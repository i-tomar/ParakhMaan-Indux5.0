"""
Object storage for uploaded images, video and evidence.

Backends: "local" (files under STORAGE_DIR) or "s3" (AWS S3 / MinIO). Code stores and passes
around *keys* such as "uploads/<inspection>/<uuid>.jpg"; OpenCV/OCR call local_path() to get a
readable file (downloaded to a local cache for S3). Browsers get short-lived HMAC-signed URLs
served by /api/v1/files, so storage is never publicly mounted.

Rows created before this abstraction hold absolute local paths; those keep working as long as the
file lives inside STORAGE_DIR.
"""
import base64
import hashlib
import hmac
import io
import mimetypes
import os
import time
import uuid
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile

from app.core.config import settings

_CHUNK = 1024 * 1024


def detect_kind(head: bytes) -> Optional[Tuple[str, str]]:
    """Identifies allowed media by magic bytes, not by the client-supplied name or content type."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image", ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", ".webp"
    if head.startswith(b"BM"):
        return "image", ".bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image", ".tif"
    if head[4:8] == b"ftyp":
        return "video", ".mov" if head[8:10] == b"qt" else ".mp4"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "video", ".avi"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video", ".mkv"
    return None


def _validate(data: bytes, expected: str) -> str:
    kind = detect_kind(data[:16])
    if not kind or kind[0] != expected:
        allowed = "JPEG, PNG, WebP, BMP or TIFF" if expected == "image" else "MP4, MOV, AVI or MKV"
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Upload {allowed}.")
    if expected == "image":
        from PIL import Image
        try:
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
        except Exception:
            raise HTTPException(status_code=400, detail="Image file is corrupt or unreadable")
        if w * h > settings.MAX_IMAGE_PIXELS:
            raise HTTPException(status_code=413, detail=f"Image is too large ({w}x{h} pixels)")
    return kind[1]


class _LocalBackend:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)

    def path(self, key: str) -> str:
        candidate = os.path.realpath(key if os.path.isabs(key) else os.path.join(self.root, key))
        if os.path.commonpath([candidate, self.root]) != self.root:
            raise HTTPException(status_code=403, detail="Path outside storage")
        return candidate

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def local_path(self, key: str) -> str:
        return self.path(key)

    def read(self, key: str) -> bytes:
        with open(self.path(key), "rb") as f:
            return f.read()

    def exists(self, key: str) -> bool:
        try:
            return os.path.exists(self.path(key))
        except HTTPException:
            return False

    def delete(self, key: str) -> None:
        path = self.path(key)
        if os.path.exists(path):
            os.remove(path)


class _S3Backend:
    def __init__(self):
        import boto3
        from botocore.config import Config

        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.S3_SECRET_KEY or None,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        self.cache = os.path.join(settings.STORAGE_DIR, "cache")
        self.local = _LocalBackend(settings.STORAGE_DIR)  # legacy absolute paths
        self._bucket_checked = False

    def _ensure_bucket(self) -> None:
        if self._bucket_checked:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)
        self._bucket_checked = True

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._ensure_bucket()
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        cached = os.path.join(self.cache, key)
        os.makedirs(os.path.dirname(cached), exist_ok=True)
        with open(cached, "wb") as f:
            f.write(data)

    def local_path(self, key: str) -> str:
        if os.path.isabs(key):
            return self.local.path(key)
        cached = os.path.realpath(os.path.join(self.cache, key))
        if not os.path.exists(cached):
            os.makedirs(os.path.dirname(cached), exist_ok=True)
            self.client.download_file(self.bucket, key, cached)
        return cached

    def read(self, key: str) -> bytes:
        if os.path.isabs(key):
            return self.local.read(key)
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        if os.path.isabs(key):
            return self.local.exists(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        if os.path.isabs(key):
            return self.local.delete(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)
        cached = os.path.join(self.cache, key)
        if os.path.exists(cached):
            os.remove(cached)


class StorageService:
    def __init__(self):
        self._backend = None

    @property
    def backend(self):
        if self._backend is None:
            self._backend = _S3Backend() if settings.STORAGE_BACKEND.lower() == "s3" else _LocalBackend(settings.STORAGE_DIR)
        return self._backend

    # --- writing ---
    async def save_upload(self, file: UploadFile, inspection_id: str, kind: str = "image") -> str:
        limit = (settings.MAX_IMAGE_MB if kind == "image" else settings.MAX_VIDEO_MB) * 1024 * 1024
        chunks, size = [], 0
        while True:
            chunk = await file.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise HTTPException(status_code=413, detail=f"File exceeds {limit // (1024 * 1024)} MB limit")
            chunks.append(chunk)
        return self.save_bytes(b"".join(chunks), inspection_id, kind=kind)

    def save_bytes(self, data: bytes, inspection_id: str, filename: str = "", kind: str = "image", prefix: str = "uploads") -> str:
        if not data:
            raise HTTPException(status_code=400, detail="Empty file")
        ext = _validate(data, kind)
        stem = os.path.splitext(os.path.basename(filename))[0] if filename else ""
        safe_stem = "".join(ch for ch in stem if ch.isalnum() or ch in "-_")[:40]
        name = f"{uuid.uuid4().hex}{('_' + safe_stem) if safe_stem else ''}{ext}"
        key = f"{prefix}/{inspection_id}/{name}"
        self.backend.put(key, data, mimetypes.guess_type(name)[0] or "application/octet-stream")
        return key

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Stores server-generated artefacts (datasets, model files) without media validation."""
        self.backend.put(key, data, content_type)
        return key

    def put_file(self, key: str, path: str, content_type: str = "application/octet-stream") -> str:
        with open(path, "rb") as f:
            return self.put_object(key, f.read(), content_type)

    # --- reading ---
    def local_path(self, key: str) -> str:
        return self.backend.local_path(key)

    def read(self, key: str) -> bytes:
        return self.backend.read(key)

    def exists(self, key: Optional[str]) -> bool:
        return bool(key) and self.backend.exists(key)

    def delete(self, key: Optional[str]) -> None:
        if not key:
            return
        try:
            self.backend.delete(key)
        except Exception:
            pass

    # --- signed URLs ---
    def _sign(self, encoded_key: str, exp: int) -> str:
        msg = f"{encoded_key}.{exp}".encode()
        return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:32]

    def signed_url(self, key: Optional[str]) -> Optional[str]:
        if not key:
            return None
        encoded = base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")
        # Expiry is bucketed to 10 minutes so the same image keeps the same URL (browser caching).
        exp = (int(time.time()) // 600 + 1) * 600 + settings.FILE_URL_TTL_SECONDS
        return f"{settings.API_V1_STR}/files/{encoded}?exp={exp}&sig={self._sign(encoded, exp)}"

    def verify(self, encoded_key: str, exp: int, sig: str) -> str:
        if exp < time.time() or not hmac.compare_digest(self._sign(encoded_key, exp), sig):
            raise HTTPException(status_code=403, detail="Invalid or expired file link")
        padded = encoded_key + "=" * (-len(encoded_key) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode()

    # --- legacy helper ---
    def get_relative_url(self, file_path: str) -> str:
        return self.signed_url(file_path) or ""


storage_service = StorageService()
