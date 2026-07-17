from collections import Counter
from time import perf_counter
from typing import Any

from prometheus_client import CollectorRegistry, Counter as PromCounter, Gauge, Histogram, generate_latest

registry = CollectorRegistry(auto_describe=True)
JOB_COUNTER = PromCounter("worker_jobs_total", "Total processed worker jobs", ["status", "file_type"], registry=registry)
JOB_DURATION = Histogram("worker_job_duration_seconds", "Worker job duration in seconds", ["file_type"], registry=registry)
JOB_FAILURES = PromCounter("worker_job_failures_total", "Total worker job failures", ["file_type"], registry=registry)
CURRENT_QUEUE = Gauge("worker_jobs_in_flight", "Worker jobs currently processing", registry=registry)


def observe_job(file_type: str, status: str, duration_seconds: float | None = None) -> None:
    JOB_COUNTER.labels(status=status, file_type=file_type).inc()
    if duration_seconds is not None:
        JOB_DURATION.labels(file_type=file_type).observe(duration_seconds)


def observe_failure(file_type: str) -> None:
    JOB_FAILURES.labels(file_type=file_type).inc()


def metrics_payload() -> bytes:
    return generate_latest(registry)
