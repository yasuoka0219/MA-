"""SendLog model for tracking message deliveries"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


class SendStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


class SendChannel(str, enum.Enum):
    EMAIL = "email"
    LINE = "line"


class SendLog(Base):
    __tablename__ = "send_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    scenario_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
    channel: Mapped[SendChannel] = mapped_column(
        Enum(SendChannel),
        nullable=False,
        default=SendChannel.EMAIL
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SendStatus] = mapped_column(
        Enum(SendStatus),
        nullable=False,
        default=SendStatus.SCHEDULED
    )
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_recipient: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    lead = relationship("Lead", backref="send_logs")
    scenario = relationship("Scenario", backref="send_logs")
