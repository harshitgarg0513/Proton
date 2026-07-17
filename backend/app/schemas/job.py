from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int
    parent_job_id: int | None = None
    chunk_index: int | None = None
    job_type: str
    profile: str
    status: str
    progress: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    processing_duration: float | None
    output_storage_path: str | None
    report_data: dict | None