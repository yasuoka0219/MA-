"""Scoring service - centralized engagement score management"""
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src.ma_tool.models.lead import Lead
from src.ma_tool.models.engagement_event import EngagementEvent
from src.ma_tool.config import get_settings

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def is_important_page(url: Optional[str]) -> bool:
    if not url:
        return False
    settings = get_settings()
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        for important_path in settings.important_page_list:
            if important_path.lower() in path:
                return True
    except Exception:
        pass
    return False


def get_score_for_event(event_type: str, url: Optional[str] = None) -> int:
    settings = get_settings()
    important = is_important_page(url)

    if event_type == "click":
        return settings.SCORE_IMPORTANT_CLICK if important else settings.SCORE_CLICK
    elif event_type == "open":
        return settings.SCORE_OPEN
    elif event_type == "page_view":
        return settings.SCORE_IMPORTANT_PAGE_VIEW if important else settings.SCORE_PAGE_VIEW
    return 0


def calculate_score_band(score: int) -> str:
    settings = get_settings()
    if score >= settings.SCORE_BAND_HOT:
        return "hot"
    elif score >= settings.SCORE_BAND_WARM:
        return "warm"
    return "cold"


def update_lead_score(db: Session, lead: Lead, points: int) -> None:
    lead.engagement_score = (lead.engagement_score or 0) + points
    lead.last_engaged_at = datetime.now(JST)
    lead.score_band = calculate_score_band(lead.engagement_score)
    db.flush()


def record_engagement(
    db: Session,
    event_type: str,
    lead_id: Optional[int] = None,
    send_log_id: Optional[int] = None,
    scenario_id: Optional[int] = None,
    calendar_event_id: Optional[int] = None,
    url: Optional[str] = None,
    referrer: Optional[str] = None,
    meta_json: Optional[str] = None,
) -> Optional[EngagementEvent]:
    event = EngagementEvent(
        lead_id=lead_id,
        send_log_id=send_log_id,
        scenario_id=scenario_id,
        calendar_event_id=calendar_event_id,
        event_type=event_type,
        url=url,
        referrer=referrer,
        meta_json=meta_json,
        occurred_at=datetime.now(JST),
    )
    db.add(event)

    if lead_id:
        lead = db.get(Lead, lead_id)
        if lead:
            points = get_score_for_event(event_type, url)
            if points > 0:
                update_lead_score(db, lead, points)
                logger.info(f"Score updated: lead_id={lead_id}, type={event_type}, +{points}, total={lead.engagement_score}, band={lead.score_band}")

    db.flush()
    return event
