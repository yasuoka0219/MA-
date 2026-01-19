"""Lead Event Registration model for linking leads to calendar events"""
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


class RegistrationStatus:
    SCHEDULED = "scheduled"
    ATTENDED = "attended"
    ABSENT = "absent"
    CANCELLED = "cancelled"


class LeadEventRegistration(Base):
    __tablename__ = "lead_event_registrations"
    __table_args__ = (
        UniqueConstraint('lead_id', 'calendar_event_id', name='uq_lead_calendar_event'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    calendar_event_id: Mapped[int] = mapped_column(Integer, ForeignKey("calendar_events.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RegistrationStatus.SCHEDULED
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    lead = relationship("Lead", backref="event_registrations")
    calendar_event = relationship("CalendarEvent", backref="registrations")
