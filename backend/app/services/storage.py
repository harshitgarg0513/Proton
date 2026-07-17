from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from minio import Minio
from starlette.datastructures import UploadFile

from app.core.config import get_settings


class MinioStorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket_name = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.ensure_bucket_exists()

    def ensure_bucket_exists(self) -> None:
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)

    def build_storage_path(self, folder: str, filename: str) -> str:
        safe_name = Path(filename).name or "upload.bin"
        return f"uploads/{folder}/{uuid4().hex}/{safe_name}"

    def upload_file(self, upload_file: UploadFile, storage_path: str, content_type: str | None = None) -> None:
        upload_file.file.seek(0)
        self.client.put_object(
            self.bucket_name,
            storage_path,
            upload_file.file,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=content_type or upload_file.content_type or "application/octet-stream",
        )

    def upload_local_file(self, local_path: str, storage_path: str, content_type: str) -> None:
        with open(local_path, "rb") as file_handle:
            file_handle.seek(0, 2)
            file_size = file_handle.tell()
            file_handle.seek(0)
            self.client.put_object(
                self.bucket_name,
                storage_path,
                file_handle,
                length=file_size,
                part_size=10 * 1024 * 1024,
                content_type=content_type,
            )

    def download_file(self, storage_path: str, destination_path: str) -> None:
        response = self.client.get_object(self.bucket_name, storage_path)
        try:
            with open(destination_path, "wb") as file_handle:
                for chunk in response.stream(32 * 1024):
                    file_handle.write(chunk)
        finally:
            response.close()
            response.release_conn()


@lru_cache(maxsize=1)
def get_storage_service() -> MinioStorageService:
    return MinioStorageService()