import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from prometheus_client.core import CollectorRegistry
from sqlalchemy import text

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.rate_limit import RateLimitMiddleware
from app.models.file import FileRecord
from app.models.job import Job

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    for _ in range(30):
        try:
            with engine.begin() as connection:
                connection.execute(text("SELECT 1"))
            break
        except Exception:  # noqa: BLE001
            time.sleep(1)

    Base.metadata.create_all(bind=engine)
    _ensure_job_chunk_columns()


def _ensure_job_chunk_columns() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS parent_job_id INTEGER "
                "REFERENCES jobs(id) ON DELETE CASCADE"
            )
        )
        connection.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS chunk_index INTEGER"))


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Proton API"}


app.include_router(router)

# Simple metrics endpoint
@app.get("/metrics")
def metrics():
    return generate_latest()
