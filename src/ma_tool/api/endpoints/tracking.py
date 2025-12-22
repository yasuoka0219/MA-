"""Email tracking endpoints (open tracking pixel)"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session
from itsdangerous import URLSafeSerializer, BadSignature

from src.ma_tool.database import get_db
from src.ma_tool.models.send_log import SendLog
from src.ma_tool.config import settings
from src.ma_tool.services.audit import log_action

router = APIRouter(prefix="/tracking")

JST = ZoneInfo("Asia/Tokyo")

TRANSPARENT_1X1_GIF = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00,
    0x80, 0x00, 0x00, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x21,
    0xf9, 0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00,
    0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
    0x01, 0x00, 0x3b
])


@router.get("/open/{token}")
def track_open(
    token: str,
    db: Session = Depends(get_db)
):
    serializer = URLSafeSerializer(settings.TRACKING_SECRET)
    
    try:
        data = serializer.loads(token)
        send_log_id = data.get("send_log_id")
        
        if send_log_id:
            send_log = db.get(SendLog, send_log_id)
            
            if send_log and send_log.opened_at is None:
                send_log.opened_at = datetime.now(JST)
                
                log_action(
                    db=db,
                    action="email_opened",
                    actor_id=None,
                    actor_role_snapshot="lead",
                    target_type="send_log",
                    target_id=send_log_id,
                    details={
                        "lead_id": send_log.lead_id,
                        "scenario_id": send_log.scenario_id
                    }
                )
                
                db.commit()
                
    except BadSignature:
        pass
    
    return FastAPIResponse(
        content=TRANSPARENT_1X1_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
