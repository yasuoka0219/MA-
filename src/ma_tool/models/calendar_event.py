"""Calendar Event model for OC, 説明会, etc."""
import enum
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Boolean, Date, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.ma_tool.models.base import Base, TimestampMixin


class EventType(str, enum.Enum):
    OC = "oc"
    BRIEFING = "briefing"
    INTERVIEW = "interview"
    TOUR = "tour"
    OTHER = "other"


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_events"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
