"""Template model with approval workflow"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Enum, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


class TemplateStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChannelType(str, enum.Enum):
    EMAIL = "email"
    LINE = "line"


class Template(Base):
    __tablename__ = "templates"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType),
        nullable=False,
        default=ChannelType.EMAIL
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flex_message_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[TemplateStatus] = mapped_column(
        Enum(TemplateStatus),
        nullable=False,
        default=TemplateStatus.DRAFT
    )
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    creator = relationship("User", foreign_keys=[created_by], backref="created_templates")
    approver = relationship("User", foreign_keys=[approved_by], backref="approved_templates")
