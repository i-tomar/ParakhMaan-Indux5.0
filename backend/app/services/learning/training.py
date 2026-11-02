"""
Training worker and evaluation gate.

MODEL_TRAINING job:
  1. builds a fresh dataset version from all verified images (unless one is given) — training on the full
     verified history acts as the replay buffer that prevents forgetting older defect types;
  2. fine-tunes YOLO starting from the active model's weights (warm start) on the train / val splits;
  3. exports ONNX (static input size, readable by OpenCV DNN) and registers a CANDIDATE model version;
  4. runs the evaluation gate on the frozen golden test split against the active model.

The gate never promotes anything — promotion is a separate, approved step (registry.promote).
"""
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.all_models import DatasetVersion, ModelVersion
from app.services import job_service
from app.services.learning import datasets
from app.services.learning.evaluation import evaluate, load_yolo
from app.services.learning.registry import learning_classes, log_event, next_version, registry, sha256_of
from app.services.storage_service import storage_service

log = logging.getLogger(__name__)

TRAINING_JOB = "MODEL_TRAINING"
EVALUATION_JOB = "MODEL_EVALUATION"


def create_training_candidate(db: Session, organization_id: str, user_id: Optional[str],
                              dataset_version_id: Optional[str] = None, notes: Optional[str] = None) -> ModelVersion:
    parent = registry.active(db, organization_id)
    version = next_version(db, organization_id)
    mv = ModelVersion(organization_id=organization_id, version=version, name=f"v{version}", status="TRAINING",
                      source="TRAINED", parent_id=parent.id if parent else None, dataset_version_id=dataset_version_id,
                      classes=learning_classes(), input_size=settings.TRAIN_IMGSZ, created_by_id=user_id, notes=notes)
    db.add(mv)
    db.commit()
    db.refresh(mv)
    return mv


# ---------------------------------------------------------------- evaluation gate
def evaluate_onnx(onnx_path: str, classes: List[str], samples) -> Dict[str, Any]:
    from app.services.defect_detection_service import DefectDetector

    det = DefectDetector(model_path=onnx_path, model_classes=",".join(classes), backend="onnx", conf_threshold=0.01)
    if not det.status()["model_loaded"]:
        raise ValueError(f"Model could not be loaded for evaluation: {det.status()['model_error']}")
    if samples:
        det.detect(samples[0][1])  # warm-up so latency is representative
    return evaluate("onnx", det, samples, iou_thr=0.5, op_conf=settings.DEFECT_MODEL_CONF_THRESHOLD,
                    classes=[c.upper() for c in classes])


def gate_decision(candidate: Dict[str, Any], champion: Optional[Dict[str, Any]], test_images: int) -> Dict[str, Any]:
    """Pure decision function: every check must pass for the candidate to be promotable."""
    checks = []

    def check(name: str, passed: bool, detail: str, value=None, threshold=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail, "value": value, "threshold": threshold})

    check("golden_set_size", test_images >= settings.GATE_MIN_TEST_IMAGES,
          f"{test_images} golden test images (minimum {settings.GATE_MIN_TEST_IMAGES})",
          test_images, settings.GATE_MIN_TEST_IMAGES)

    if champion:
        floor = champion["map50"] - settings.GATE_MAP_TOLERANCE
        check("map50_not_worse", candidate["map50"] >= floor,
              f"mAP@0.5 {candidate['map50']:.3f} vs active {champion['map50']:.3f}", candidate["map50"], round(floor, 3))
        for cls, cm in candidate["per_class"].items():
            base = champion["per_class"].get(cls, {})
            if base.get("gt", 0) < settings.GATE_MIN_CLASS_SUPPORT:
                continue
            drop = base.get("recall", 0.0) - cm["recall"]
            check(f"recall_{cls.lower()}", drop <= settings.GATE_MAX_CLASS_RECALL_DROP,
                  f"{cls} recall {cm['recall']:.3f} vs active {base.get('recall', 0.0):.3f}",
                  cm["recall"], round(base.get("recall", 0.0) - settings.GATE_MAX_CLASS_RECALL_DROP, 3))
        if champion.get("avg_latency_ms"):
            limit = champion["avg_latency_ms"] * settings.GATE_MAX_LATENCY_RATIO
            check("latency", candidate["avg_latency_ms"] <= limit,
                  f"{candidate['avg_latency_ms']:.1f} ms vs active {champion['avg_latency_ms']:.1f} ms",
                  candidate["avg_latency_ms"], round(limit, 1))

    critical = candidate["per_class"].get(settings.GATE_CRITICAL_CLASS.upper())
    if critical and critical["gt"] >= settings.GATE_MIN_CLASS_SUPPORT:
        check("critical_class_recall", critical["recall"] >= settings.GATE_CRITICAL_MIN_RECALL,
              f"{settings.GATE_CRITICAL_CLASS} recall {critical['recall']:.3f} (minimum {settings.GATE_CRITICAL_MIN_RECALL})",
              critical["recall"], settings.GATE_CRITICAL_MIN_RECALL)

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "checks": checks, "candidate": candidate, "champion": champion,
            "test_images": test_images, "evaluated_at": datetime.now(timezone.utc).isoformat()}


def run_gate(db: Session, mv: ModelVersion, ds: DatasetVersion, progress=None) -> Dict[str, Any]:
    folder = datasets.extract_dataset(ds)
    try:
        classes = ds.classes or learning_classes()
        samples = list(load_yolo(folder, classes, split="test"))
        if progress:
            progress(0.9, f"Scoring candidate on {len(samples)} golden test images")
        candidate = evaluate_onnx(storage_service.local_path(mv.onnx_key), classes, samples) if samples else None
        champion_mv = registry.active(db, mv.organization_id)
        champion = None
        if champion_mv and champion_mv.id != mv.id and champion_mv.onnx_key and samples:
            if progress:
                progress(0.95, f"Scoring active model {champion_mv.name}")
            champion = evaluate_onnx(storage_service.local_path(champion_mv.onnx_key), champion_mv.classes or classes, samples)
        empty = {"map50": 0.0, "precision": 0.0, "recall": 0.0, "avg_latency_ms": 0.0, "per_class": {}}
        report = gate_decision(candidate or empty, champion, len(samples))
        report["dataset_version"] = ds.version
        report["champion_name"] = champion_mv.name if champion_mv and champion else None
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    mv.gate_report = report
    mv.status = "GATE_PASSED" if report["passed"] else "GATE_FAILED"
    failed = [c["name"] for c in report["checks"] if not c["passed"]]
    log_event(db, mv.organization_id, "GATE_EVALUATED",
              f"{mv.name} {'passed' if report['passed'] else 'failed'} the evaluation gate"
              + (f" ({', '.join(failed)})" if failed else ""), mv, payload={"passed": report["passed"], "failed": failed})
    db.commit()
    return report


# ---------------------------------------------------------------- training
def _train(mv: ModelVersion, ds_folder: str, base_weights: str, progress=None) -> Dict[str, Any]:
    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise RuntimeError("Training requires the 'ultralytics' package (build the worker image with TRAINING=true)") from e

    classes = mv.classes or learning_classes()
    has_val = any(os.scandir(os.path.join(ds_folder, "images", "val")))
    yaml_path = os.path.join(ds_folder, "train.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(f"path: {ds_folder.replace(os.sep, '/')}\ntrain: images/train\n")
        # YOLO needs a validation split; with too few batches the train split stands in (noted in the metrics).
        f.write(f"val: images/{'val' if has_val else 'train'}\n")
        f.write(f"nc: {len(classes)}\nnames: {classes}\n")

    model = YOLO(base_weights)
    epochs = settings.TRAIN_EPOCHS

    def on_epoch_end(trainer):
        if progress:
            progress(0.15 + 0.65 * (trainer.epoch + 1) / epochs, f"Training epoch {trainer.epoch + 1}/{epochs}")

    model.add_callback("on_train_epoch_end", on_epoch_end)
    run_dir = os.path.join(ds_folder, "runs")
    started = time.perf_counter()
    model.train(data=yaml_path, epochs=epochs, imgsz=settings.TRAIN_IMGSZ, batch=settings.TRAIN_BATCH,
                device=settings.TRAIN_DEVICE, workers=0, project=run_dir, name="train", exist_ok=True,
                verbose=False, plots=False, seed=0, deterministic=True)
    duration = time.perf_counter() - started
    best = os.path.join(run_dir, "train", "weights", "best.pt")
    if not os.path.exists(best):
        best = os.path.join(run_dir, "train", "weights", "last.pt")
    metrics = {k.replace("metrics/", "").replace("(B)", ""): round(float(v), 4)
               for k, v in (getattr(model.trainer, "metrics", None) or {}).items() if k.startswith("metrics/")}
    if progress:
        progress(0.82, "Exporting ONNX")
    exported = YOLO(best).export(format="onnx", imgsz=settings.TRAIN_IMGSZ, opset=12, simplify=False, dynamic=False)
    return {"pt": best, "onnx": str(exported), "metrics": metrics, "duration_s": round(duration, 1),
            "validation_split": "val" if has_val else "train (insufficient batches for a separate val split)"}


@job_service.register(TRAINING_JOB)
def run_training_job(db: Session, job, progress) -> Dict[str, Any]:
    payload = job.payload or {}
    mv = db.get(ModelVersion, payload["model_version_id"])
    mv.job_id = job.id
    db.commit()
    try:
        ds = db.get(DatasetVersion, mv.dataset_version_id) if mv.dataset_version_id else None
        if ds is None or ds.status != "READY":
            progress(0.02, "Building dataset from verified images")
            ds = datasets.create_dataset_version(db, mv.organization_id, job.created_by_id,
                                                 notes=f"Built for training {mv.name}")
            datasets.build_dataset(db, ds, lambda f, m=None: progress(0.02 + f * 0.12, m))
            mv.dataset_version_id = ds.id
            db.commit()
        if (ds.split_counts or {}).get("train", 0) == 0:
            raise ValueError("Dataset has no training images — verify more images in the review queue first")

        parent = db.get(ModelVersion, mv.parent_id) if mv.parent_id else None
        base = storage_service.local_path(parent.pt_key) if parent and parent.pt_key else settings.TRAIN_BASE_WEIGHTS
        log_event(db, mv.organization_id, "TRAINING_STARTED",
                  f"Training {mv.name} on dataset v{ds.version} from {parent.name if parent and parent.pt_key else base}", mv)
        db.commit()

        folder = datasets.extract_dataset(ds)
        try:
            out = _train(mv, folder, base, progress)
            prefix = f"models/{mv.organization_id}/v{mv.version}"
            mv.onnx_key = storage_service.put_file(f"{prefix}/model.onnx", out["onnx"])
            mv.pt_key = storage_service.put_file(f"{prefix}/model.pt", out["pt"])
            mv.sha256 = sha256_of(out["onnx"])
        finally:
            shutil.rmtree(folder, ignore_errors=True)

        mv.train_metrics = {**out["metrics"], "duration_s": out["duration_s"], "validation_split": out["validation_split"]}
        mv.model_card = {
            "name": f"ParakhMaan defect model {mv.name}", "classes": mv.classes, "input_size": settings.TRAIN_IMGSZ,
            "warm_start_from": parent.name if parent and parent.pt_key else settings.TRAIN_BASE_WEIGHTS,
            "dataset_version": ds.version, "dataset_manifest_sha256": ds.manifest_sha256,
            "dataset_split_counts": ds.split_counts, "dataset_class_counts": ds.class_counts,
            "training": {"epochs": settings.TRAIN_EPOCHS, "batch": settings.TRAIN_BATCH, "device": settings.TRAIN_DEVICE},
            "validation_metrics": out["metrics"],
            "intended_use": "Surface defect localisation for the products present in the training data",
            "limitations": ["Accuracy only established for the product families and capture setups in the dataset",
                            "Golden-set metrics are reported in the gate report"],
        }
        mv.status = "CANDIDATE"
        log_event(db, mv.organization_id, "TRAINING_COMPLETED",
                  f"{mv.name} trained in {out['duration_s']} s (val mAP@0.5 {out['metrics'].get('mAP50', 0):.3f})", mv)
        db.commit()

        report = run_gate(db, mv, ds, progress)
        return {"model_version_id": mv.id, "name": mv.name, "status": mv.status, "gate_passed": report["passed"],
                "train_metrics": mv.train_metrics, "dataset_version": ds.version}
    except Exception as e:
        db.rollback()
        mv = db.get(ModelVersion, payload["model_version_id"])
        mv.status = "FAILED"
        log_event(db, mv.organization_id, "TRAINING_FAILED", f"{mv.name} training failed: {str(e)[:300]}", mv)
        db.commit()
        raise


@job_service.register(EVALUATION_JOB)
def run_evaluation_job(db: Session, job, progress) -> Dict[str, Any]:
    payload = job.payload or {}
    mv = db.get(ModelVersion, payload["model_version_id"])
    ds = db.get(DatasetVersion, payload.get("dataset_version_id") or mv.dataset_version_id)
    if ds is None or ds.status != "READY":
        raise ValueError("A READY dataset version is required for evaluation")
    previous_status = mv.status
    report = run_gate(db, mv, ds, progress)
    if previous_status in ("ACTIVE", "SHADOW", "RETIRED"):
        mv.status = previous_status  # re-evaluating does not demote a model that is already in use
        db.commit()
    return {"model_version_id": mv.id, "passed": report["passed"], "dataset_version": ds.version}
