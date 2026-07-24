from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import SessionLocal
from app.models.file import FileRecord
from app.models.job import Job
from app.services.storage import get_storage_service
from app.processors.audio_processor import AudioProcessor
from app.processors.image_processor import ImageProcessor
from app.processors.pdf_processor import PdfProcessor
from app.processors.video_processor import VideoOptimizationResult, VideoProcessor
from app.services.fallback import keep_original_if_larger


def _detect_file_type(file_record: FileRecord) -> str:
    mime_type = (file_record.mime_type or "").lower()
    file_name = (file_record.filename or "").lower()
    if mime_type.startswith("image/") or Path(file_name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
        return mime_type or "image/unknown"
    if mime_type.startswith("video/") or Path(file_name).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
        return mime_type or "video/unknown"
    if mime_type == "application/pdf" or Path(file_name).suffix.lower() == ".pdf":
        return "application/pdf"
    if mime_type.startswith("audio/") or Path(file_name).suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}:
        return mime_type or "audio/unknown"
    return mime_type or "application/octet-stream"


def _is_image(file_record: FileRecord) -> bool:
    mime_type = (file_record.mime_type or "").lower()
    file_name = (file_record.filename or "").lower()
    return mime_type.startswith("image/") or Path(file_name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".avif"}


def _is_video(file_record: FileRecord) -> bool:
    mime_type = (file_record.mime_type or "").lower()
    file_name = (file_record.filename or "").lower()
    return mime_type.startswith("video/") or Path(file_name).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}


def _is_pdf(file_record: FileRecord) -> bool:
    mime_type = (file_record.mime_type or "").lower()
    file_name = (file_record.filename or "").lower()
    return mime_type == "application/pdf" or Path(file_name).suffix.lower() == ".pdf"


def _is_audio(file_record: FileRecord) -> bool:
    mime_type = (file_record.mime_type or "").lower()
    file_name = (file_record.filename or "").lower()
    return mime_type.startswith("audio/") or Path(file_name).suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def _update_job(session, job: Job, **changes) -> Job:
    for key, value in changes.items():
        setattr(job, key, value)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _mark_failure(session, job_id: int, message: str) -> None:
    job = session.get(Job, job_id)
    if job is None:
        return

    _update_job(
        session,
        job,
        status="FAILED",
        error_message=message,
        completed_at=datetime.now(timezone.utc),
        processing_duration=(datetime.now(timezone.utc) - (job.started_at or datetime.now(timezone.utc))).total_seconds(),
    )


def process_compression_job(job_id: int) -> None:
    session = SessionLocal()
    started_at = datetime.now(timezone.utc)
    storage_service = get_storage_service()

    try:
        job = session.get(Job, job_id)
        if job is None:
            return

        file_record = session.get(FileRecord, job.file_id)
        if file_record is None:
            _update_job(
                session,
                job,
                status="FAILED",
                error_message="Associated file record not found",
                completed_at=datetime.now(timezone.utc),
            )
            return

        _update_job(session, job, status="PROCESSING", progress=10, started_at=started_at, error_message=None)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / Path(file_record.storage_path).name
            storage_service.download_file(file_record.storage_path, str(source_path))

            output_dir = temp_path / "outputs"
            if _is_image(file_record):
                processor = ImageProcessor(str(source_path), job.profile, str(output_dir))
            elif _is_video(file_record):
                processor = VideoProcessor(str(source_path), job.profile, str(output_dir))
            elif _is_pdf(file_record):
                processor = PdfProcessor(str(source_path), job.profile, str(output_dir))
            elif _is_audio(file_record):
                processor = AudioProcessor(str(source_path), job.profile, str(output_dir))
            else:
                raise ValueError("Only image, video, PDF, and audio processing are enabled in this phase")

            analysis = processor.analyze()
            _update_job(session, job, progress=25)

            # Skip chunking for synchronous execution
            optimization = processor.optimize()
            _update_job(session, job, progress=70)

            optimized_path = optimization["optimized_path"]
            optimized_storage_path = storage_service.build_storage_path("optimized", Path(optimized_path).name)
            optimized_content_type = "video/mp4" if optimized_path.endswith(".mp4") else "image/webp"
            if optimized_path.endswith(".avif"):
                optimized_content_type = "image/avif"
            if optimized_path.endswith(".pdf"):
                optimized_content_type = "application/pdf"
            if optimized_path.endswith(".opus"):
                optimized_content_type = "audio/opus"
            if optimized_path.endswith(".m4a"):
                optimized_content_type = "audio/mp4"
            storage_service.upload_local_file(
                optimized_path,
                optimized_storage_path,
                content_type=optimized_content_type,
            )

            thumbnail_storage_path = None
            if optimization.get("thumbnail_path"):
                thumbnail_path = optimization["thumbnail_path"]
                thumbnail_storage_path = storage_service.build_storage_path("thumbnails", Path(thumbnail_path).name)
                thumbnail_content_type = "image/webp" if thumbnail_path.endswith(".webp") else "image/jpeg"
                storage_service.upload_local_file(thumbnail_path, thumbnail_storage_path, content_type=thumbnail_content_type)

            report = processor.generate_report()
            report["original_storage_path"] = file_record.storage_path
            report["thumbnail_storage_path"] = thumbnail_storage_path
            report["optimized_storage_path"] = optimized_storage_path

            processing_duration = (datetime.now(timezone.utc) - started_at).total_seconds()
            _update_job(
                session,
                job,
                status="COMPLETED",
                progress=100,
                completed_at=datetime.now(timezone.utc),
                processing_duration=processing_duration,
                output_storage_path=optimized_storage_path,
                report_data=report,
            )

            file_record.upload_status = "optimized"
            session.add(file_record)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        _mark_failure(session, job_id, str(exc))
        raise
    finally:
        session.close()
