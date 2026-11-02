import mimetypes
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app.services.storage_service import storage_service

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("/{encoded_key}")
def get_file(encoded_key: str, exp: int = Query(...), sig: str = Query(...)):
    """Serves stored media for a valid signed link (used by <img> tags, which cannot send auth headers)."""
    key = storage_service.verify(encoded_key, exp, sig)
    if not storage_service.exists(key):
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    headers = {"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"}
    path = storage_service.local_path(key)
    if os.path.exists(path):
        return FileResponse(path, media_type=media_type, headers=headers)
    return Response(storage_service.read(key), media_type=media_type, headers=headers)
