"""Authenticated access to stored images and PDFs.

Replaces the old public `/storage` mount, which served every file under STORAGE_DIR without login,
including the SQLite database when it lives there (as it does in Docker). Only image and PDF files
inside STORAGE_DIR are served; models, databases and anything outside the folder are refused.
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings

router = APIRouter(prefix="/files", tags=["Files"])

SERVABLE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".bmp": "image/bmp",
            ".webp": "image/webp", ".pdf": "application/pdf"}
NEVER = ("models", "_registry", "_versions")


def resolve_storage_file(relative: str) -> str:
    root = os.path.realpath(settings.STORAGE_DIR)
    rel = relative.replace("\\", "/").lstrip("/")
    if rel.startswith("storage/"):
        rel = rel[len("storage/"):]
    path = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([root, path]) != root:
        raise HTTPException(status_code=403, detail="Outside storage")
    if any(part in NEVER for part in os.path.relpath(path, root).split(os.sep)):
        raise HTTPException(status_code=403, detail="Not a servable file")
    if os.path.splitext(path)[1].lower() not in SERVABLE:
        raise HTTPException(status_code=403, detail="Not a servable file")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return path


@router.get("/{relative:path}")
def get_file(relative: str):
    path = resolve_storage_file(relative)
    return FileResponse(path, media_type=SERVABLE[os.path.splitext(path)[1].lower()],
                        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})
