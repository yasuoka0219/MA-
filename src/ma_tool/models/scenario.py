"""Scenario model for Step2 send engine"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


class BaseDateType:
    LEAD_CREATED_AT = "lead_created_at"
    EVENT_DATE = "event_date"


class Scenario(Base):
    __tablename__ = "scenarios"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("templates.id"), nullable=False)
    trigger_event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frequency_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    graduation_year_rule: Mapped[str] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    base_date_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=BaseDateType.LEAD_CREATED_AT
    )
    event_type_filter: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_calendar_event_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("calendar_events.id"),
        nullable=True
    )
    
    segment_graduation_year_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    segment_graduation_year_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    segment_grade_in: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    segment_prefecture: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    segment_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    segment_school_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    segment_event_status_in: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
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
    
    template = relationship("Template", backref="scenarios")
    target_calendar_event = relationship("CalendarEvent", backref="scenarios")
    
    def has_segment_conditions(self) -> bool:
        """Check if any segment conditions are set"""
        return any([
            self.segment_graduation_year_from,
            self.segment_graduation_year_to,
            self.segment_grade_in,
            self.segment_prefecture,
            self.segment_tag,
            self.segment_school_name,
            self.segment_event_status_in,
        ])
    
    def get_segment_summary(self) -> str:
        """Get a short summary of segment conditions"""
        parts = []
        if self.segment_graduation_year_from or self.segment_graduation_year_to:
            from_year = self.segment_graduation_year_from or "〜"
            to_year = self.segment_graduation_year_to or "〜"
            if from_year == to_year:
                parts.append(f"卒年:{from_year}")
            else:
                parts.append(f"卒年:{from_year}-{to_year}")
        if self.segment_grade_in:
            parts.append(f"学年:{self.segment_grade_in}")
        if self.segment_prefecture:
            parts.append(f"都道府県:{self.segment_prefecture}")
        if self.segment_school_name:
            parts.append(f"高校:{self.segment_school_name}")
        if self.segment_tag:
            parts.append(f"タグ:{self.segment_tag}")
        if self.segment_event_status_in:
            parts.append(f"参加ステータス:{self.segment_event_status_in}")
        return " / ".join(parts) if parts else "—"
