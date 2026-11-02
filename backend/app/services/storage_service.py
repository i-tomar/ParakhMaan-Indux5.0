import os
import uuid
import shutil
from fastapi import HTTPException, UploadFile
from app.core.config import settings

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

class StorageService:
    """
    Local storage service with abstraction for MinIO/S3.
    """

    def __init__(self):
        self.upload_dir = os.path.join(settings.STORAGE_DIR, "uploads")
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_upload(self, file: UploadFile, inspection_id: str, kind: str = "image") -> str:
        insp_dir = os.path.join(self.upload_dir, inspection_id)
        os.makedirs(insp_dir, exist_ok=True)

        allowed, limit_mb = (VIDEO_EXTENSIONS, settings.MAX_VIDEO_MB) if kind == "video" else (IMAGE_EXTENSIONS, settings.MAX_UPLOAD_MB)
        ext = (os.path.splitext(file.filename or "")[1] or ".jpg").lower()
        if ext not in allowed:
            raise HTTPException(status_code=415, detail=f"Unsupported file type '{ext}'")

        unique_filename = f"{uuid.uuid4()}{ext}"
        target_path = os.path.join(insp_dir, unique_filename)

        content = await file.read(limit_mb * 1024 * 1024 + 1)
        if len(content) > limit_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File exceeds the {limit_mb} MB limit")
        with open(target_path, "wb") as out_file:
            out_file.write(content)

        return target_path

    def save_bytes(self, image_bytes: bytes, inspection_id: str, filename: str = "capture.jpg") -> str:
        insp_dir = os.path.join(self.upload_dir, inspection_id)
        os.makedirs(insp_dir, exist_ok=True)

        unique_filename = f"{uuid.uuid4()}_{filename}"
        target_path = os.path.join(insp_dir, unique_filename)

        with open(target_path, "wb") as out_file:
            out_file.write(image_bytes)

        return target_path

    def get_relative_url(self, file_path: str) -> str:
        # Converts local absolute path to static served URL
        normalized = file_path.replace("\\", "/")
        if "storage" in normalized:
            idx = normalized.find("storage")
            return "/" + normalized[idx:]
        return file_path

storage_service = StorageService()
