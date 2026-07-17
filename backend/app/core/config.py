from dataclasses import dataclass
import os


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Proton API")
    api_prefix: str = os.getenv("API_PREFIX", "/api")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@postgres:5432/proton",
    )
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "uploads")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    cors_origins: tuple[str, ...] = _split_csv(
        os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    )
    max_upload_size_bytes: int = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024)))


_settings = Settings()


def get_settings() -> Settings:
    return _settings