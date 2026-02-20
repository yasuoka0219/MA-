"""WebSession model - tracks site visits per tracking_id"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


class WebSession(Base):
    __tablename__ = "web_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    pageviews: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    lead = relationship("Lead", backref="web_sessions")
