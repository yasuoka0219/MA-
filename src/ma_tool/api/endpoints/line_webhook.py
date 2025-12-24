"""LINE Webhook endpoint for handling messaging events"""
from datetime import datetime, timezone
from typing import Optional
import hashlib
import hmac
import base64
import logging

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from src.ma_tool.config import settings
from src.ma_tool.database import get_db
from src.ma_tool.models.line_identity import LineIdentity, LineIdentityStatus
from src.ma_tool.models.lead import Lead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["LINE Webhook"])


def verify_signature(body: bytes, signature: str) -> bool:
    if not settings.LINE_CHANNEL_SECRET:
        logger.error("LINE_CHANNEL_SECRET not configured - webhook requests blocked")
        return False
    
    if not signature:
        logger.warning("Missing X-Line-Signature header")
        return False
    
    hash_value = hmac.new(
        settings.LINE_CHANNEL_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(hash_value).decode('utf-8')
    
    return hmac.compare_digest(signature, expected_signature)


def handle_follow_event(event: dict, db: Session) -> None:
    source = event.get("source", {})
    user_id = source.get("userId")
    
    if not user_id:
        logger.warning("Follow event missing userId")
        return
    
    existing = db.query(LineIdentity).filter(
        LineIdentity.line_user_id == user_id
    ).first()
    
    if existing:
        if existing.lead_id:
            lead = db.query(Lead).filter(Lead.id == existing.lead_id).first()
            if lead:
                lead.line_blocked = False
                db.commit()
        logger.info(f"LINE user {user_id} already registered")
        return
    
    identity = LineIdentity(
        line_user_id=user_id,
        status=LineIdentityStatus.UNLINKED
    )
    db.add(identity)
    db.commit()
    
    logger.info(f"New LINE user registered: {user_id}")


def handle_unfollow_event(event: dict, db: Session) -> None:
    source = event.get("source", {})
    user_id = source.get("userId")
    
    if not user_id:
        logger.warning("Unfollow event missing userId")
        return
    
    identity = db.query(LineIdentity).filter(
        LineIdentity.line_user_id == user_id
    ).first()
    
    if identity and identity.lead_id:
        lead = db.query(Lead).filter(Lead.id == identity.lead_id).first()
        if lead:
            lead.line_blocked = True
            db.commit()
    
    logger.info(f"LINE user unfollowed: {user_id}")


def handle_message_event(event: dict, db: Session) -> None:
    source = event.get("source", {})
    user_id = source.get("userId")
    message = event.get("message", {})
    message_type = message.get("type")
    
    if not user_id:
        logger.warning("Message event missing userId")
        return
    
    if message_type != "text":
        logger.info(f"Ignoring non-text message from {user_id}")
        return
    
    text = message.get("text", "").strip()
    
    if text.startswith("LINK:"):
        handle_link_command(user_id, text[5:].strip(), db)
    else:
        logger.info(f"Received text message from {user_id}: {text[:50]}...")


LINE_LINK_SALT = "line-link-token"
LINE_LINK_TOKEN_MAX_AGE = 3600


def generate_line_link_token(lead_id: int) -> str:
    serializer = URLSafeTimedSerializer(settings.UNSUBSCRIBE_SECRET)
    return serializer.dumps({"lead_id": lead_id}, salt=LINE_LINK_SALT)


def verify_line_link_token(token: str) -> Optional[int]:
    serializer = URLSafeTimedSerializer(settings.UNSUBSCRIBE_SECRET)
    try:
        data = serializer.loads(token, salt=LINE_LINK_SALT, max_age=LINE_LINK_TOKEN_MAX_AGE)
        return data.get("lead_id")
    except (BadSignature, SignatureExpired):
        return None


def handle_link_command(line_user_id: str, code: str, db: Session) -> None:
    identity = db.query(LineIdentity).filter(
        LineIdentity.line_user_id == line_user_id
    ).first()
    
    if not identity:
        identity = LineIdentity(
            line_user_id=line_user_id,
            status=LineIdentityStatus.UNLINKED
        )
        db.add(identity)
        db.commit()
    
    if identity.status == LineIdentityStatus.LINKED:
        logger.info(f"LINE user {line_user_id} is already linked")
        return
    
    lead_id = verify_line_link_token(code)
    
    if not lead_id:
        logger.warning(f"Invalid or expired link token from LINE user {line_user_id}")
        return
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    
    if not lead:
        logger.warning(f"Lead {lead_id} not found for link token")
        return
    
    identity.lead_id = lead.id
    identity.status = LineIdentityStatus.LINKED
    identity.linked_at = datetime.now(timezone.utc)
    db.commit()
    
    logger.info(f"LINE user {line_user_id} linked to lead {lead.id} via secure token")


@router.post("/line")
async def line_webhook(
    request: Request,
    x_line_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    body = await request.body()
    
    if not verify_signature(body, x_line_signature or ""):
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    events = payload.get("events", [])
    
    for event in events:
        event_type = event.get("type")
        
        try:
            if event_type == "follow":
                handle_follow_event(event, db)
            elif event_type == "unfollow":
                handle_unfollow_event(event, db)
            elif event_type == "message":
                handle_message_event(event, db)
            else:
                logger.info(f"Ignoring event type: {event_type}")
        except Exception as e:
            logger.exception(f"Error handling {event_type} event: {e}")
    
    return {"status": "ok"}
