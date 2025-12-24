"""LINE Identity model for managing LINE user connections"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ma_tool.models.base import Base


class LineIdentityStatus(str, enum.Enum):
    UNLINKED = "unlinked"
    LINKED = "linked"


class LineIdentity(Base):
    __tablename__ = "line_identities"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    line_user_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    status: Mapped[LineIdentityStatus] = mapped_column(
        Enum(LineIdentityStatus),
        nullable=False,
        default=LineIdentityStatus.UNLINKED
    )
    linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    lead = relationship("Lead", backref="line_identities")
