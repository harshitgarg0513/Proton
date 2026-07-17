from app.workers.celery_app import celery_app
from worker.tasks import compression_tasks  # noqa: F401

__all__ = ["celery_app"]
