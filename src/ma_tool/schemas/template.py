"""Pydantic schemas for template management"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from src.ma_tool.models.template import TemplateStatus


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(..., min_length=1, max_length=500)
    body_html: str = Field(..., min_length=1)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    subject: Optional[str] = Field(None, min_length=1, max_length=500)
    body_html: Optional[str] = Field(None, min_length=1)


class TemplateReject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class TemplateClone(BaseModel):
    new_name: Optional[str] = Field(None, max_length=255)


class TemplateResponse(BaseModel):
    id: int
    name: str
    subject: str
    body_html: str
    status: TemplateStatus
    created_by: int
    created_by_name: Optional[str] = None
    approved_by: Optional[int] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    templates: List[TemplateResponse]
    total: int


class VariableInfo(BaseModel):
    name: str
    description: str
