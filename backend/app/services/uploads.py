import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings


class UploadValidationError(ValueError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class BufferedUpload:
    file_obj: tempfile.SpooledTemporaryFile
    size_bytes: int
    checksum_sha256: str


async def validate_and_buffer_upload(upload: UploadFile, settings: Settings) -> BufferedUpload:
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm", ".mkv"}:
        raise UploadValidationError("Unsupported video file extension.", 415)
    if (upload.content_type or "").lower() not in settings.allowed_video_types:
        raise UploadValidationError("Unsupported video content type.", 415)

    buffered = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_size_bytes:
                raise UploadValidationError("Video exceeds the maximum upload size.", 413)
            digest.update(chunk)
            buffered.write(chunk)
    except Exception:
        buffered.close()
        raise
    buffered.seek(0)
    return BufferedUpload(buffered, size, digest.hexdigest())
