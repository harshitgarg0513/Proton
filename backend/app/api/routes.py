import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Final

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.auth import get_current_owner
from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.models.file import FileRecord
from app.models.job import Job
from app.services.job_dispatcher import dispatch_compression_job
from app.schemas.file import UploadResponse
from app.schemas.job import JobRead
from app.services.storage import get_storage_service

settings = get_settings()
TERMINAL_JOB_STATUSES = frozenset({"COMPLETED", "FAILED"})
JOB_STREAM_POLL_INTERVAL_SECONDS = 1.0
ALLOWED_UPLOAD_TYPES: Final[set[str]] = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/avif",
    "image/gif",
    "image/svg+xml",
    "application/pdf",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
    "audio/flac",
    "audio/aac",
    "audio/x-m4a",
}

router = APIRouter(prefix=settings.api_prefix)


def _get_upload_size(file: UploadFile) -> int:
    try:
        if hasattr(file, "size") and file.size is not None and file.size > 0:
            return file.size
    except Exception:
        pass

    try:
        stream = file.file
        if getattr(stream, "closed", False):
            return 0
        current_position = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(current_position)
        return size
    except Exception:
        return 0


def _detect_file_type(file: UploadFile) -> str:
    try:
        stream = file.file
        if not getattr(stream, "closed", False):
            current_position = stream.tell()
            stream.seek(0)
            header = stream.read(512)
            stream.seek(current_position)

            if header.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if header.startswith(b"RIFF") and b"WEBP" in header[:12]:
                return "image/webp"
            if header.startswith(b"ftyp") or b"ftyp" in header[:32]:
                if b"avif" in header.lower():
                    return "image/avif"
                if b"M4A " in header or b"mp42" in header:
                    return "audio/mp4"
                return "video/mp4"
            if header.startswith(b"%PDF-"):
                return "application/pdf"
            if header.startswith(b"ID3") or header.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
                return "audio/mpeg"
            if header.startswith(b"RIFF") and b"WAVE" in header[8:16]:
                return "audio/wav"
            if header.startswith(b"OggS"):
                return "audio/ogg"
            if header.startswith(b"\x1aE\xdf\xa3"):
                return "video/webm"
            if header.startswith(b"fLaC"):
                return "audio/flac"
    except Exception:
        pass

    content_type = (file.content_type or "").lower()
    if content_type in ALLOWED_UPLOAD_TYPES:
        return content_type

    filename = (file.filename or "").lower()
    ext_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".avif": "image/avif",
        ".pdf": "application/pdf",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
    }
    for ext, mime in ext_map.items():
        if filename.endswith(ext):
            return mime

    raise ValueError(f"Unsupported file format for {file.filename or 'uploaded file'}")


def _validate_upload_file(file: UploadFile, size: int, max_size_bytes: int) -> str:
    detected_type = _detect_file_type(file)
    if detected_type not in ALLOWED_UPLOAD_TYPES:
        raise ValueError("Unsupported file type")

    if size > max_size_bytes:
        raise ValueError("File exceeds the configured upload size limit")

    return detected_type


@router.post("/files/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    profile: str = Form("balanced"),
    owner: str = Depends(get_current_owner),
    db: Session = Depends(get_db),
):
    try:
        file_size = _get_upload_size(file)
        detected_type = _validate_upload_file(file, file_size, settings.max_upload_size_bytes)
        storage_service = get_storage_service()
        storage_path = storage_service.build_storage_path("original", file.filename or "upload.bin")
        storage_service.upload_file(file, storage_path, content_type=detected_type)

        file_record = FileRecord(
            owner_id=owner,
            filename=file.filename or "upload.bin",
            original_size=file_size,
            mime_type=detected_type,
            storage_path=storage_path,
            upload_status="uploaded",
        )
        db.add(file_record)
        db.flush()

        job = Job(
            owner_id=owner,
            file_id=file_record.id,
            job_type="compression",
            profile=profile,
            status="PENDING",
            progress=0,
        )
        db.add(job)
        db.commit()
        db.refresh(file_record)
        db.refresh(job)

        background_tasks.add_task(dispatch_compression_job, job.id)

        return {
            "file": file_record,
            "job": job,
        }
    except ValueError as exc:
        logger.error(f"Upload failed (ValueError/Validation/Boto): {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Upload failed (Unexpected Exception): {exc}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(owner: str = Depends(get_current_owner), db: Session = Depends(get_db)):
    jobs = db.query(Job).filter(Job.owner_id == owner).order_by(Job.id.desc()).all()
    return jobs


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, owner: str = Depends(get_current_owner), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or job.owner_id != owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return job


def _fetch_job(job_id: int, owner: str) -> Job | None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or job.owner_id != owner:
            return None
        return job
    finally:
        db.close()


async def _job_stream(job_id: int, owner: str) -> AsyncIterator[str]:
    last_snapshot: tuple[int, str] | None = None

    while True:
        job = _fetch_job(job_id, owner)
        if job is None:
            yield f"event: error\ndata: {json.dumps({'detail': 'Job not found'})}\n\n"
            break

        snapshot = (job.progress, job.status)
        if snapshot != last_snapshot:
            job_data = JobRead.model_validate(job).model_dump(mode="json")
            yield f"event: job\ndata: {json.dumps(job_data)}\n\n"
            last_snapshot = snapshot

            if job.status.upper() in TERMINAL_JOB_STATUSES:
                yield "event: done\ndata: {}\n\n"
                break

        await asyncio.sleep(JOB_STREAM_POLL_INTERVAL_SECONDS)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int, owner: str = Depends(get_current_owner)):
    job = _fetch_job(job_id, owner)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return StreamingResponse(
        _job_stream(job_id, owner),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
def health_check():
    return {"status": "ok"}