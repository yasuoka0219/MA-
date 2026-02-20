"""SendGrid Event Webhook endpoint"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel

from src.ma_tool.database import get_db
from src.ma_tool.models.send_log import SendLog
from src.ma_tool.services.scoring import record_engagement

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhooks"])


class SendGridEvent(BaseModel):
    event: str
    sg_message_id: Optional[str] = None
    email: Optional[str] = None
    timestamp: Optional[int] = None
    url: Optional[str] = None


@router.post("/webhooks/sendgrid")
async def sendgrid_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    if not isinstance(body, list):
        body = [body]

    processed = 0
    for event_data in body:
        try:
            event_type = event_data.get("event", "")
            sg_message_id = event_data.get("sg_message_id", "")

            if sg_message_id and "." in sg_message_id:
                sg_message_id = sg_message_id.split(".")[0]

            if event_type == "open" and sg_message_id:
                send_log = db.execute(
                    select(SendLog).where(SendLog.provider_message_id == sg_message_id)
                ).scalar_one_or_none()

                if send_log:
                    record_engagement(
                        db,
                        event_type="open",
                        lead_id=send_log.lead_id,
                        send_log_id=send_log.id,
                        scenario_id=send_log.scenario_id,
                        calendar_event_id=send_log.calendar_event_id,
                    )
                    processed += 1

            elif event_type in ("bounce", "spamreport", "unsubscribe") and sg_message_id:
                send_log = db.execute(
                    select(SendLog).where(SendLog.provider_message_id == sg_message_id)
                ).scalar_one_or_none()

                if send_log and send_log.lead_id:
                    record_engagement(
                        db,
                        event_type=event_type,
                        lead_id=send_log.lead_id,
                        send_log_id=send_log.id,
                        scenario_id=send_log.scenario_id,
                    )
                    processed += 1

        except Exception as e:
            logger.error(f"Error processing SendGrid event: {e}")

    db.commit()
    logger.info(f"SendGrid webhook processed: {processed}/{len(body)} events")
    return JSONResponse({"ok": True, "processed": processed})
