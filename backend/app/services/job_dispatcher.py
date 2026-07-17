from app.tasks.compression_tasks import process_compression_job


def dispatch_compression_job(job_id: int) -> None:
    # Execute compression synchronously (no worker on free plan)
    process_compression_job(job_id)