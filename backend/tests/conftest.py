import os
import tempfile

# Settings are read at import time, so the test database and storage must be
# configured before any `app` module is imported.
_TMP = tempfile.mkdtemp(prefix="sih_tests_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("REPORTS_DIR", os.path.join(_TMP, "storage", "reports"))
os.environ.setdefault("DEFECT_SAMPLES_DIR", os.path.join(_TMP, "storage", "defect_samples"))
# Keep API / OpenCV assertions deterministic; tests that need the ONNX model load it explicitly.
os.environ["DEFECT_MODEL_PATH"] = ""
