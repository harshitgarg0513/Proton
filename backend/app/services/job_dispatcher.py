from app.workers.celery_app import celery_app


COMPRESSION_TASK_NAME = "worker.tasks.compression_tasks.process_compression_job"


def dispatch_compression_job(job_id: int) -> None:
    celery_app.send_task(COMPRESSION_TASK_NAME, args=[job_id])