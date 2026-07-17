from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from celery import chord, group
from celery.exceptions import MaxRetriesExceededError

from app.core.database import SessionLocal
from app.models.file import FileRecord
from app.models.job import Job
from app.services.storage import get_storage_service
from app.workers.celery_app import celery_app
from worker.processors.audio_processor import AudioProcessor
from worker.processors.image_processor import ImageProcessor
from worker.processors.pdf_processor import PdfProcessor
from worker.processors.video_processor import VideoOptimizationResult, VideoProcessor
from worker.metrics import CURRENT_QUEUE, observe_failure, observe_job
from worker.services.chunking.video_chunker import VideoChunker
from worker.services.fallback import keep_original_if_larger
from worker.services.quality.video_quality import VideoQualityMetric


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


def _mark_chunk_failure(session, chunk_job_id: int, parent_job_id: int, message: str) -> None:
    chunk_job = session.get(Job, chunk_job_id)
    if chunk_job is not None:
        _update_job(
            session,
            chunk_job,
            status="FAILED",
            error_message=message,
            completed_at=datetime.now(timezone.utc),
        )
    _mark_failure(session, parent_job_id, message)


def _start_chunked_video_job(
    session,
    job: Job,
    file_record: FileRecord,
    processor: VideoProcessor,
    analysis: dict,
    source_path: Path,
    storage_service,
    temp_path: Path,
    started_at: datetime,
) -> None:
    duration = float(analysis.get("duration") or 0.0)
    processor.prepare_encode_plan()

    split_result = VideoChunker(str(source_path), str(temp_path / "chunking")).split(duration)
    chunk_count = len(split_result.chunk_paths)

    orchestration = {
        "chunked": True,
        "chunk_count": chunk_count,
        "chunk_jobs_completed": 0,
        "chunk_jobs_total": chunk_count,
        "analysis": analysis,
        "encode_plan": VideoProcessor.plan_to_dict(processor.plan),
        "recommendation": processor.recommendation,
        "benchmark_results": processor.benchmark_results,
        "chunk_plan": {
            "chunk_count": split_result.plan.chunk_count,
            "chunk_length_seconds": split_result.plan.chunk_length_seconds,
            "chunk_directory": split_result.plan.chunk_directory,
        },
        "started_at": started_at.isoformat(),
    }
    _update_job(session, job, status="PROCESSING", progress=20, report_data=orchestration)

    chunk_signatures = []
    for chunk_index, chunk_path in enumerate(split_result.chunk_paths):
        chunk_storage_path = storage_service.build_storage_path("chunks", f"job_{job.id}_chunk_{chunk_index}.mp4")
        storage_service.upload_local_file(chunk_path, chunk_storage_path, content_type="video/mp4")

        chunk_job = Job(
            file_id=file_record.id,
            parent_job_id=job.id,
            chunk_index=chunk_index,
            job_type="compression_chunk",
            profile=job.profile,
            status="PENDING",
            progress=0,
        )
        session.add(chunk_job)
        session.flush()

        chunk_signatures.append(
            process_video_chunk.s(
                chunk_job.id,
                chunk_storage_path,
                job.id,
                chunk_index,
                chunk_count,
            )
        )

    session.commit()
    chord(group(chunk_signatures))(merge_video_chunks.s(job.id))


@celery_app.task(bind=True, name="worker.tasks.compression_tasks.process_compression_job", max_retries=3)
def process_compression_job(self, job_id: int) -> None:
    session = SessionLocal()
    started_at = datetime.now(timezone.utc)
    storage_service = get_storage_service()
    CURRENT_QUEUE.inc()

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

            if isinstance(processor, VideoProcessor) and VideoProcessor.should_chunk(
                job.profile,
                float(analysis.get("duration") or 0.0),
            ):
                _start_chunked_video_job(
                    session,
                    job,
                    file_record,
                    processor,
                    analysis,
                    source_path,
                    storage_service,
                    temp_path,
                    started_at,
                )
                return

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
            observe_job(file_type=_detect_file_type(file_record), status="completed", duration_seconds=processing_duration)
            session.add(file_record)
            session.commit()
    except MaxRetriesExceededError:
        _mark_failure(session, job_id, "Maximum retry attempts exceeded")
        observe_failure(_detect_file_type(file_record) if "file_record" in locals() else "unknown")
        raise
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries:
            job = session.get(Job, job_id)
            if job is not None:
                _update_job(session, job, status="RETRYING", progress=job.progress, error_message=str(exc))
            raise self.retry(exc=exc, countdown=5)

        _mark_failure(session, job_id, str(exc))
        observe_failure(_detect_file_type(file_record) if "file_record" in locals() else "unknown")
        raise
    finally:
        CURRENT_QUEUE.dec()
        session.close()


@celery_app.task(bind=True, name="worker.tasks.compression_tasks.process_video_chunk", max_retries=3)
def process_video_chunk(
    self,
    chunk_job_id: int,
    chunk_storage_path: str,
    parent_job_id: int,
    chunk_index: int,
    chunk_count: int,
) -> dict:
    session = SessionLocal()
    storage_service = get_storage_service()

    try:
        chunk_job = session.get(Job, chunk_job_id)
        parent_job = session.get(Job, parent_job_id)
        if chunk_job is None or parent_job is None:
            raise RuntimeError("Chunk or parent job not found")

        orchestration = parent_job.report_data or {}
        analysis = orchestration.get("analysis")
        encode_plan = orchestration.get("encode_plan")
        if not analysis or not encode_plan:
            raise RuntimeError("Missing chunk orchestration metadata on parent job")

        _update_job(
            session,
            chunk_job,
            status="PROCESSING",
            progress=10,
            started_at=datetime.now(timezone.utc),
            error_message=None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / f"chunk_{chunk_index}.mp4"
            output_dir = temp_path / "output"
            storage_service.download_file(chunk_storage_path, str(source_path))

            processor = VideoProcessor(str(source_path), chunk_job.profile, str(output_dir))
            processor.analysis = analysis
            processor.plan = VideoProcessor.plan_from_dict(encode_plan)
            processor.benchmark_results = orchestration.get("benchmark_results")
            processor.recommendation = orchestration.get("recommendation")

            result = processor.optimize_chunk()

            optimized_storage_path = storage_service.build_storage_path(
                "chunks",
                f"job_{parent_job_id}_chunk_{chunk_index}_optimized.mp4",
            )
            storage_service.upload_local_file(
                result["optimized_path"],
                optimized_storage_path,
                content_type="video/mp4",
            )

            _update_job(
                session,
                chunk_job,
                status="COMPLETED",
                progress=100,
                completed_at=datetime.now(timezone.utc),
                output_storage_path=optimized_storage_path,
                report_data={
                    "chunk_index": chunk_index,
                    "optimized_size": result["optimized_size"],
                    "optimization_applied": result["optimization_applied"],
                    "codec_used": result["codec_used"],
                },
            )

            completed_chunks = (
                session.query(Job)
                .filter(
                    Job.parent_job_id == parent_job_id,
                    Job.status == "COMPLETED",
                )
                .count()
            )
            chunk_progress = 25 + int((completed_chunks / chunk_count) * 55)
            orchestration = dict(parent_job.report_data or {})
            orchestration["chunk_jobs_completed"] = completed_chunks
            orchestration["chunk_jobs_total"] = chunk_count
            _update_job(session, parent_job, progress=min(chunk_progress, 80), report_data=orchestration)

            return {
                "chunk_index": chunk_index,
                "output_storage_path": optimized_storage_path,
                "optimized_size": result["optimized_size"],
                "optimization_applied": result["optimization_applied"],
            }
    except MaxRetriesExceededError:
        _mark_chunk_failure(session, chunk_job_id, parent_job_id, "Maximum retry attempts exceeded for chunk")
        raise
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries:
            chunk_job = session.get(Job, chunk_job_id)
            if chunk_job is not None:
                _update_job(session, chunk_job, status="RETRYING", progress=chunk_job.progress, error_message=str(exc))
            raise self.retry(exc=exc, countdown=5)

        _mark_chunk_failure(session, chunk_job_id, parent_job_id, str(exc))
        raise
    finally:
        session.close()


@celery_app.task(bind=True, name="worker.tasks.compression_tasks.merge_video_chunks", max_retries=1)
def merge_video_chunks(self, chunk_results: list[dict], parent_job_id: int) -> None:
    session = SessionLocal()
    storage_service = get_storage_service()

    try:
        parent_job = session.get(Job, parent_job_id)
        if parent_job is None:
            return

        file_record = session.get(FileRecord, parent_job.file_id)
        if file_record is None:
            _mark_failure(session, parent_job_id, "Associated file record not found during chunk merge")
            return

        orchestration = parent_job.report_data or {}
        started_at_raw = orchestration.get("started_at")
        started_at = datetime.fromisoformat(started_at_raw) if started_at_raw else parent_job.started_at or datetime.now(timezone.utc)

        _update_job(session, parent_job, status="PROCESSING", progress=85, error_message=None)

        sorted_results = sorted(chunk_results, key=lambda item: item["chunk_index"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            local_chunks: list[str] = []
            for result in sorted_results:
                local_path = temp_path / f"merged_chunk_{result['chunk_index']}.mp4"
                storage_service.download_file(result["output_storage_path"], str(local_path))
                local_chunks.append(str(local_path))

            source_path = temp_path / Path(file_record.storage_path).name
            storage_service.download_file(file_record.storage_path, str(source_path))

            output_dir = temp_path / "outputs"
            output_dir.mkdir(parents=True, exist_ok=True)
            merged_path = output_dir / f"{Path(file_record.filename).stem}.mp4"
            VideoProcessor.merge_chunks(local_chunks, str(merged_path))

            analysis = orchestration.get("analysis") or {}
            processor = VideoProcessor(str(source_path), parent_job.profile, str(output_dir))
            processor.analysis = analysis
            processor.plan = VideoProcessor.plan_from_dict(orchestration["encode_plan"])
            processor.benchmark_results = orchestration.get("benchmark_results")
            processor.recommendation = orchestration.get("recommendation")
            processor.chunk_plan = orchestration.get("chunk_plan")

            thumbnail_path = output_dir / f"{Path(source_path).stem}_thumb.jpg"
            processor._extract_thumbnail(str(thumbnail_path), analysis)

            optimized_path, optimized_size, optimization_applied = keep_original_if_larger(str(source_path), str(merged_path))
            processor.quality_metrics = VideoQualityMetric(str(source_path), str(optimized_path)).compute()
            processor.recommendation = {
                **(processor.recommendation or {}),
                "optimization_applied": optimization_applied,
                "optimization_result": (
                    "Chunked compression applied successfully."
                    if optimization_applied
                    else "Original video retained because merged optimization increased file size."
                ),
                "chunked_processing": True,
                "chunks_merged": len(sorted_results),
            }

            processing_duration = (datetime.now(timezone.utc) - started_at).total_seconds()
            processor.result = VideoOptimizationResult(
                optimized_path=str(optimized_path),
                thumbnail_path=str(thumbnail_path),
                codec_used=processor.plan.codec,
                format_after="MP4",
                optimized_size=optimized_size,
                processing_time=processing_duration,
                optimization_applied=optimization_applied,
            )

            optimized_storage_path = storage_service.build_storage_path("optimized", Path(optimized_path).name)
            storage_service.upload_local_file(str(optimized_path), optimized_storage_path, content_type="video/mp4")

            thumbnail_storage_path = None
            if Path(thumbnail_path).exists():
                thumbnail_storage_path = storage_service.build_storage_path("thumbnails", thumbnail_path.name)
                storage_service.upload_local_file(str(thumbnail_path), thumbnail_storage_path, content_type="image/jpeg")

            report = processor.generate_report()
            report["thumbnail_storage_path"] = thumbnail_storage_path
            report["optimized_storage_path"] = optimized_storage_path
            report["chunk_jobs_completed"] = len(sorted_results)
            report["chunk_jobs_total"] = orchestration.get("chunk_count", len(sorted_results))

            _update_job(
                session,
                parent_job,
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
    except MaxRetriesExceededError:
        _mark_failure(session, parent_job_id, "Maximum retry attempts exceeded during chunk merge")
        raise
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries:
            parent_job = session.get(Job, parent_job_id)
            if parent_job is not None:
                _update_job(session, parent_job, status="RETRYING", progress=parent_job.progress, error_message=str(exc))
            raise self.retry(exc=exc, countdown=5)

        _mark_failure(session, parent_job_id, str(exc))
        raise
    finally:
        session.close()
