"""Lead schemas"""
from typing import Optional, List
from pydantic import BaseModel, EmailStr


class LeadBase(BaseModel):
    email: EmailStr
    name: str
    school_name: Optional[str] = None
    graduation_year: int
    interest_tags: Optional[str] = None
    consent: bool


class LeadCreate(LeadBase):
    pass


class LeadResponse(LeadBase):
    id: int
    unsubscribed: bool
    
    class Config:
        from_attributes = True


class CSVImportResult(BaseModel):
    added: int
    updated: int
    errors: List[dict]
    total_processed: int
