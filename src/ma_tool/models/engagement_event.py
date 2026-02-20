"""EngagementEvent model - tracks user engagement actions"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


class EngagementEventType(str, enum.Enum):
    OPEN = "open"
    CLICK = "click"
    PAGE_VIEW = "page_view"
    SESSION_START = "session_start"
    BOUNCE = "bounce"
    SPAMREPORT = "spamreport"
    UNSUBSCRIBE = "unsubscribe"


class EngagementEvent(Base):
    __tablename__ = "engagement_events"
    __table_args__ = (
        Index("ix_engagement_events_lead_occurred", "lead_id", "occurred_at"),
        Index("ix_engagement_events_type_occurred", "event_type", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    send_log_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("send_logs.id"), nullable=True, index=True)
    scenario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    calendar_event_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    lead = relationship("Lead", backref="engagement_events")
    send_log = relationship("SendLog", backref="engagement_events")
