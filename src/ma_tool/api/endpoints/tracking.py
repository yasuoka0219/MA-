"""Email tracking endpoints (open tracking pixel, click redirect, page view)"""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, urlencode, urlunparse, parse_qs
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from itsdangerous import URLSafeSerializer, BadSignature
from pydantic import BaseModel

from src.ma_tool.database import get_db
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.send_log import SendLog
from src.ma_tool.models.web_session import WebSession
from src.ma_tool.services.scoring import record_engagement
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
    settings = get_settings()
    serializer = URLSafeSerializer(settings.TRACKING_SECRET)
    return serializer.dumps({"send_log_id": send_log_id})


def generate_click_token(
    send_log_id: int,
    lead_id: int,
    target_url: str,
    scenario_id: Optional[int] = None,
    calendar_event_id: Optional[int] = None,
) -> str:
    settings = get_settings()
    serializer = URLSafeSerializer(settings.TRACKING_SECRET)
    payload = {
        "sl": send_log_id,
        "l": lead_id,
        "u": target_url,
    }
    if scenario_id:
        payload["sc"] = scenario_id
    if calendar_event_id:
        payload["ce"] = calendar_event_id
    return serializer.dumps(payload)


def get_tracking_pixel_url(send_log_id: int, base_url: str = "") -> str:
    token = generate_tracking_token(send_log_id)
    return f"{base_url}/t/open/{token}.png"


def get_click_tracking_url(
    send_log_id: int,
    lead_id: int,
    target_url: str,
    base_url: str = "",
    scenario_id: Optional[int] = None,
    calendar_event_id: Optional[int] = None,
) -> str:
    token = generate_click_token(send_log_id, lead_id, target_url, scenario_id, calendar_event_id)
    return f"{base_url}/t/c/{token}"


@router.get("/open/{token}.png")
def track_open(
    token: str,
    db: Session = Depends(get_db)
):
    settings = get_settings()
    serializer = URLSafeSerializer(settings.TRACKING_SECRET)

    try:
        data = serializer.loads(token)
        send_log_id = data.get("send_log_id")

        if send_log_id:
            send_log = db.get(SendLog, send_log_id)

            if send_log:
                if send_log.opened_at is None:
                    send_log.opened_at = datetime.now(JST)

                record_engagement(
                    db,
                    event_type="open",
                    lead_id=send_log.lead_id,
                    send_log_id=send_log_id,
                    scenario_id=send_log.scenario_id,
                    calendar_event_id=send_log.calendar_event_id,
                )
                db.commit()
                logger.info(f"Email opened: send_log_id={send_log_id}")

    except BadSignature:
        logger.warning("Invalid tracking token received")
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


@router.get("/c/{token}")
def track_click(
    token: str,
    db: Session = Depends(get_db)
):
    settings = get_settings()
    serializer = URLSafeSerializer(settings.TRACKING_SECRET)
    fallback_url = settings.BASE_URL

    try:
        data = serializer.loads(token)
        send_log_id = data.get("sl")
        lead_id = data.get("l")
        target_url = data.get("u")
        scenario_id = data.get("sc")
        calendar_event_id = data.get("ce")

        if not target_url:
            return RedirectResponse(url=fallback_url, status_code=302)

        if lead_id:
            lead = db.get(Lead, lead_id)
            if lead and not lead.tracking_id:
                lead.tracking_id = str(uuid.uuid4())
                db.flush()

            record_engagement(
                db,
                event_type="click",
                lead_id=lead_id,
                send_log_id=send_log_id,
                scenario_id=scenario_id,
                calendar_event_id=calendar_event_id,
                url=target_url,
            )

            if lead and lead.tracking_id:
                parsed = urlparse(target_url)
                qs = parse_qs(parsed.query)
                qs["tid"] = [lead.tracking_id]
                new_query = urlencode(qs, doseq=True)
                target_url = urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path,
                    parsed.params, new_query, parsed.fragment
                ))

        db.commit()
        logger.info(f"Click tracked: send_log_id={send_log_id}, lead_id={lead_id}, url={target_url[:100]}")
        return RedirectResponse(url=target_url, status_code=302)

    except BadSignature:
        logger.warning("Invalid click token received")
        return RedirectResponse(url=fallback_url, status_code=302)
    except Exception as e:
        logger.error(f"Error processing click tracking: {e}")
        return RedirectResponse(url=fallback_url, status_code=302)


class PageViewRequest(BaseModel):
    tid: str
    url: str
    referrer: Optional[str] = None
    ts: Optional[float] = None


def _cors_headers(request: Request) -> dict:
    settings = get_settings()
    origin = request.headers.get("origin", "")
    allowed = settings.tracking_allowed_origins_list

    if allowed and origin not in allowed:
        return {}

    return {
        "Access-Control-Allow-Origin": origin or "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
    }


@router.options("/pv")
async def page_view_preflight(request: Request):
    headers = _cors_headers(request)
    if not headers:
        return Response(status_code=403)
    return Response(status_code=200, headers=headers)


@router.post("/pv")
async def track_page_view(
    request: Request,
    body: PageViewRequest,
    db: Session = Depends(get_db),
):
    headers = _cors_headers(request)
    if not headers:
        return Response(status_code=403)

    tid = body.tid.strip()
    if not tid or len(tid) > 64:
        return JSONResponse({"ok": False}, status_code=400, headers=headers)

    lead = db.execute(
        select(Lead).where(Lead.tracking_id == tid)
    ).scalar_one_or_none()

    lead_id = lead.id if lead else None

    now = datetime.now(JST)
    session_timeout_minutes = 30
    session = db.execute(
        select(WebSession)
        .where(WebSession.tracking_id == tid)
        .order_by(WebSession.last_seen_at.desc())
    ).scalar_one_or_none()

    if session and (now - session.last_seen_at.replace(tzinfo=JST if session.last_seen_at.tzinfo is None else session.last_seen_at.tzinfo)).total_seconds() < session_timeout_minutes * 60:
        session.last_seen_at = now
        session.pageviews += 1
        if lead_id and not session.lead_id:
            session.lead_id = lead_id
    else:
        session = WebSession(
            tracking_id=tid,
            lead_id=lead_id,
            started_at=now,
            last_seen_at=now,
            pageviews=1,
        )
        db.add(session)

    record_engagement(
        db,
        event_type="page_view",
        lead_id=lead_id,
        url=body.url,
        referrer=body.referrer,
        meta_json=json.dumps({"tid": tid}) if tid else None,
    )

    db.commit()
    logger.info(f"Page view tracked: tid={tid[:8]}..., lead_id={lead_id}, url={body.url[:80]}")
    return JSONResponse({"ok": True}, headers=headers)


@router.get("/snippet.js")
async def tracking_snippet(request: Request):
    settings = get_settings()
    base_url = settings.BASE_URL

    js_code = f"""
// MA Tool Tracking Snippet
(function() {{
  var MA_PV_URL = "{base_url}/t/pv";
  var COOKIE_NAME = "ma_tid";
  var COOKIE_DAYS = 365;

  function getCookie(name) {{
    var m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : null;
  }}

  function setCookie(name, val, days) {{
    var d = new Date();
    d.setTime(d.getTime() + days * 86400000);
    document.cookie = name + "=" + encodeURIComponent(val) + ";expires=" + d.toUTCString() + ";path=/;SameSite=Lax";
  }}

  var params = new URLSearchParams(window.location.search);
  var tidParam = params.get("tid");
  if (tidParam) {{
    setCookie(COOKIE_NAME, tidParam, COOKIE_DAYS);
  }}

  var tid = getCookie(COOKIE_NAME);
  if (!tid) return;

  var payload = {{
    tid: tid,
    url: window.location.href,
    referrer: document.referrer || null,
    ts: Date.now() / 1000
  }};

  try {{
    if (navigator.sendBeacon) {{
      navigator.sendBeacon(MA_PV_URL, JSON.stringify(payload));
    }} else {{
      fetch(MA_PV_URL, {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify(payload),
        keepalive: true
      }});
    }}
  }} catch(e) {{}}
}})();
"""
    return Response(
        content=js_code.strip(),
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Type": "application/javascript; charset=utf-8",
        }
    )
