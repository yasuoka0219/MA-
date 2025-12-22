"""Unsubscribe service with signed tokens"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.config import settings
from src.ma_tool.models.lead import Lead


def generate_unsubscribe_token(lead_id: int) -> str:
    serializer = URLSafeTimedSerializer(settings.UNSUBSCRIBE_SECRET)
    return serializer.dumps({"lead_id": lead_id})


def verify_unsubscribe_token(token: str, max_age: int = 60 * 60 * 24 * 365) -> int | None:
    serializer = URLSafeTimedSerializer(settings.UNSUBSCRIBE_SECRET)
    try:
        data = serializer.loads(token, max_age=max_age)
        return data.get("lead_id")
    except (BadSignature, SignatureExpired):
        return None


def process_unsubscribe(db: Session, lead_id: int) -> Lead | None:
    lead = db.execute(
        select(Lead).where(Lead.id == lead_id)
    ).scalar_one_or_none()
    
    if lead:
        lead.unsubscribed = True
        db.commit()
        db.refresh(lead)
    
    return lead
