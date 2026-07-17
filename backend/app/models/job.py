from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String(64), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    chunk_index = Column(Integer, nullable=True)
    job_type = Column(String(100), nullable=False)
    profile = Column(String(50), nullable=False, default="balanced")
    status = Column(String(50), nullable=False, default="PENDING")
    progress = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_duration = Column(Float, nullable=True)
    output_storage_path = Column(String(512), nullable=True)
    report_data = Column(JSON, nullable=True)

    file = relationship("FileRecord")
    parent_job = relationship("Job", remote_side=[id], backref="chunk_jobs")