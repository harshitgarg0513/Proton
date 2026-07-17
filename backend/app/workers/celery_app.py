from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "adaptive_content_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    task_default_queue="compression",
    task_routes={"worker.tasks.compression_tasks.*": {"queue": "compression"}},
    task_time_limit=900,
    task_soft_time_limit=780,
)