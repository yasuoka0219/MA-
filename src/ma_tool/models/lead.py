"""Lead model - students/high school students"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, Text, DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column

from src.ma_tool.models.base import Base


class GraduationYearSource(str, enum.Enum):
    CSV = "csv"
    ESTIMATED = "estimated"


class Lead(Base):
    __tablename__ = "leads"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    graduation_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    graduation_year_source: Mapped[GraduationYearSource] = mapped_column(
        Enum(GraduationYearSource),
        nullable=False,
        default=GraduationYearSource.CSV,
        server_default="CSV"
    )
    interest_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unsubscribed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
