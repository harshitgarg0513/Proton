from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.client import Config
from starlette.datastructures import UploadFile

from app.core.config import get_settings


class S3StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket_name = (settings.storage_bucket or "uploads").strip()
        endpoint_url = (settings.storage_endpoint or "minio:9000").strip()
        if not endpoint_url.startswith("http://") and not endpoint_url.startswith("https://"):
            endpoint_url = f"https://{endpoint_url}" if settings.storage_secure else f"http://{endpoint_url}"

        access_key = (settings.storage_access_key or "").strip()
        secret_key = (settings.storage_secret_key or "").strip()
        region = (settings.storage_region or "auto").strip()

        self.client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version='s3v4'),
        )
        self.ensure_bucket_exists()

    def ensure_bucket_exists(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket_name)
            except Exception:
                # Cloudflare R2 buckets are pre-created in dashboard and object-level tokens don't support bucket management APIs
                pass

    def build_storage_path(self, folder: str, filename: str) -> str:
        safe_name = Path(filename).name or "upload.bin"
        return f"uploads/{folder}/{uuid4().hex}/{safe_name}"

    def upload_file(self, upload_file: UploadFile, storage_path: str, content_type: str | None = None) -> None:
        upload_file.file.seek(0)
        self.client.upload_fileobj(
            upload_file.file,
            self.bucket_name,
            storage_path,
            ExtraArgs={'ContentType': content_type or upload_file.content_type or "application/octet-stream"},
        )

    def upload_local_file(self, local_path: str, storage_path: str, content_type: str) -> None:
        self.client.upload_file(
            local_path,
            self.bucket_name,
            storage_path,
            ExtraArgs={'ContentType': content_type},
        )

    def download_file(self, storage_path: str, destination_path: str) -> None:
        self.client.download_file(self.bucket_name, storage_path, destination_path)


@lru_cache(maxsize=1)
def get_storage_service() -> S3StorageService:
    return S3StorageService()