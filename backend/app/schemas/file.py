from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.job import JobRead


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    original_size: int
    mime_type: str
    storage_path: str
    upload_status: str
    created_at: datetime


class UploadResponse(BaseModel):
    file: FileRead
    job: JobRead