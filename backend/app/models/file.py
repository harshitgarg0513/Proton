from sqlalchemy import Column, DateTime, Integer, String, func

from app.core.database import Base


class FileRecord(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String(64), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    original_size = Column(Integer, nullable=False)
    mime_type = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False, unique=True, index=True)
    upload_status = Column(String(50), nullable=False, default="uploaded")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)