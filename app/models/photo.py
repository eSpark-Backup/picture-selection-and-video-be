from sqlalchemy import Column, String, ForeignKey, DateTime, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database.connection import Base

class Photo(Base):
    __tablename__ = "photos"

    photo_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    s3_url = Column(String(500), nullable=False)
    face_data = Column(JSON, nullable=True)  # For red-circle adjustment
    filename = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")  # pending / approved / rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="photos")
