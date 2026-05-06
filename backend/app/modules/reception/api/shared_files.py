from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.modules.reception.shared_files import reception_shared_files_service


router = APIRouter()


@router.get("/{token}/download")
def download_reception_shared_file(token: str) -> FileResponse:
    record = reception_shared_files_service.resolve_download(token)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="shared file not found")

    file_path = str(record.get("storage_path") or "").strip()
    file_name = str(record.get("file_name") or "").strip() or "attachment"
    media_type = str(record.get("mime_type") or "").strip() or "application/octet-stream"
    return FileResponse(
        path=file_path,
        filename=file_name,
        media_type=media_type,
    )

