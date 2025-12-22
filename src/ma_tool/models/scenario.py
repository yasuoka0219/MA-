"""Scenario model for Step2 send engine"""
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


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
