"""Email tracking endpoints (open tracking pixel)"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from itsdangerous import URLSafeSerializer, BadSignature

from src.ma_tool.database import get_db
from src.ma_tool.models.send_log import SendLog
from src.ma_tool.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/t", tags=["Tracking"])

JST = ZoneInfo("Asia/Tokyo")

TRANSPARENT_1X1_PNG = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00,
    0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01,
    0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1F,
    0x15, 0xC4, 0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
    0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00, 0x05, 0x00,
    0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
    0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82
])


def generate_tracking_token(send_log_id: int) -> str:
    """Generate a signed token for tracking pixel URL"""
    settings = get_settings()
    serializer = URLSafeSerializer(settings.TRACKING_SECRET)
    return serializer.dumps({"send_log_id": send_log_id})


def get_tracking_pixel_url(send_log_id: int, base_url: str = "") -> str:
    """Generate the full tracking pixel URL for embedding in email HTML"""
    token = generate_tracking_token(send_log_id)
    return f"{base_url}/t/open/{token}.png"


@router.get("/open/{token}.png")
def track_open(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Tracking pixel endpoint.
    Records email open on first access, returns 1x1 transparent PNG.
    Token contains signed send_log_id to prevent tampering.
    """
    settings = get_settings()
    serializer = URLSafeSerializer(settings.TRACKING_SECRET)
    
    try:
        data = serializer.loads(token)
        send_log_id = data.get("send_log_id")
        
        if send_log_id:
            send_log = db.get(SendLog, send_log_id)
            
            if send_log and send_log.opened_at is None:
                send_log.opened_at = datetime.now(JST)
                db.commit()
                logger.info(f"Email opened: send_log_id={send_log_id}")
                
    except BadSignature:
        logger.warning(f"Invalid tracking token received")
    except Exception as e:
        logger.error(f"Error processing tracking pixel: {e}")
    
    return Response(
        content=TRANSPARENT_1X1_PNG,
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
