"""APScheduler-based scenario runner with rate limiting and retry"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_, update
from sqlalchemy.orm import Session

from src.ma_tool.database import SessionLocal
from src.ma_tool.models.send_log import SendLog, SendStatus
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.template import Template
from src.ma_tool.models.event import Event
from src.ma_tool.services.email import EmailService, EmailMessage, get_email_service
from src.ma_tool.services.audit import log_action
from sqlalchemy.exc import IntegrityError
from src.ma_tool.services.scenario_engine import (
    find_matching_scenarios,
    evaluate_scenario_for_lead,
    create_send_log_reservation,
)
from src.ma_tool.services.template_renderer import render_email_body, render_subject
from src.ma_tool.config import get_settings

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")

RATE_LIMIT_PER_MINUTE = 60
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_MINUTES = [1, 4, 9]


def get_pending_send_logs(db: Session, now: datetime, limit: int = RATE_LIMIT_PER_MINUTE) -> list[SendLog]:
    stmt = select(SendLog).where(
        and_(
            SendLog.status == SendStatus.SCHEDULED,
            SendLog.scheduled_for <= now,
            SendLog.attempt_count < MAX_RETRY_ATTEMPTS
        )
    ).order_by(SendLog.scheduled_for).limit(limit)
    
    return list(db.execute(stmt).scalars().all())


def generate_tracking_pixel_url(send_log_id: int) -> str:
    settings = get_settings()
    base_url = getattr(settings, 'BASE_URL', 'https://example.com')
    secret = settings.TRACKING_SECRET
    from itsdangerous import URLSafeSerializer
    serializer = URLSafeSerializer(secret)
    token = serializer.dumps({"send_log_id": send_log_id})
    return f"{base_url}/tracking/open/{token}"


def inject_tracking_pixel(html_body: str, send_log_id: int) -> str:
    pixel_url = generate_tracking_pixel_url(send_log_id)
    pixel_tag = f'<img src="{pixel_url}" width="1" height="1" style="display:none" alt="" />'
    if '</body>' in html_body.lower():
        idx = html_body.lower().rfind('</body>')
        return html_body[:idx] + pixel_tag + html_body[idx:]
    return html_body + pixel_tag


def send_single_email(
    db: Session,
    send_log: SendLog,
    email_service: EmailService
) -> bool:
    try:
        lead = db.get(Lead, send_log.lead_id)
        scenario = db.get(Scenario, send_log.scenario_id)
        template = db.get(Template, scenario.template_id) if scenario else None
        
        if not all([lead, scenario, template]):
            send_log.status = SendStatus.FAILED
            send_log.error_message = "Missing lead, scenario, or template"
            return False
        
        rendered_body = render_email_body(template.body_html or "", lead)
        html_with_tracking = inject_tracking_pixel(rendered_body, send_log.id)
        
        subject = render_subject(template.subject or "", lead)
        
        send_log.attempt_count += 1
        send_log.original_recipient = lead.email
        
        settings = get_settings()
        message = EmailMessage(
            to_email=lead.email,
            subject=subject,
            html_content=html_with_tracking,
            reply_to=settings.MAIL_REPLY_TO if settings.MAIL_REPLY_TO else None
        )
        result = email_service.send(message)
        
        if result.success:
            send_log.status = SendStatus.SENT
            send_log.sent_at = datetime.now(JST)
            send_log.error_message = None
            
            log_action(
                db=db,
                action="email_sent",
                actor_id=None,
                actor_role_snapshot="system",
                target_type="send_log",
                target_id=send_log.id,
                details={
                    "lead_id": lead.id,
                    "scenario_id": scenario.id,
                    "recipient": result.actual_recipient
                }
            )
            return True
        else:
            if send_log.attempt_count >= MAX_RETRY_ATTEMPTS:
                send_log.status = SendStatus.FAILED
            else:
                backoff = RETRY_BACKOFF_MINUTES[min(send_log.attempt_count - 1, len(RETRY_BACKOFF_MINUTES) - 1)]
                send_log.scheduled_for = datetime.now(JST) + timedelta(minutes=backoff)
            
            send_log.error_message = result.message
            
            log_action(
                db=db,
                action="email_failed",
                actor_id=None,
                actor_role_snapshot="system",
                target_type="send_log",
                target_id=send_log.id,
                details={
                    "lead_id": lead.id,
                    "attempt": send_log.attempt_count,
                    "error": result.message
                }
            )
            return False
            
    except Exception as e:
        logger.exception(f"Error sending email for send_log {send_log.id}")
        send_log.status = SendStatus.FAILED
        send_log.error_message = str(e)
        return False


def process_new_events(db: Session, now: Optional[datetime] = None) -> int:
    if now is None:
        now = datetime.now(JST)
    
    lookback = now - timedelta(days=30)
    stmt = select(Event).where(Event.created_at >= lookback)
    events = list(db.execute(stmt).scalars().all())
    
    created_count = 0
    for event in events:
        scenarios = find_matching_scenarios(db, event.type)
        lead = db.get(Lead, event.lead_id)
        
        if not lead:
            continue
        
        for scenario in scenarios:
            should_send, scheduled_for, reason = evaluate_scenario_for_lead(
                db, scenario, lead, event, now
            )
            
            if should_send and scheduled_for:
                try:
                    create_send_log_reservation(db, lead, scenario, event, scheduled_for)
                    db.commit()
                    created_count += 1
                    
                    log_action(
                        db=db,
                        action="send_log_reserved",
                        actor_id=None,
                        actor_role_snapshot="system",
                        target_type="send_log",
                        target_id=None,
                        details={
                            "lead_id": lead.id,
                            "scenario_id": scenario.id,
                            "event_id": event.id,
                            "scheduled_for": scheduled_for.isoformat()
                        }
                    )
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.debug(f"Skipping duplicate: lead={lead.id}, scenario={scenario.id}")
                except Exception as e:
                    db.rollback()
                    logger.warning(f"Error creating send_log: {e}")
    
    return created_count


def run_scheduler_tick():
    logger.info("Scheduler tick started")
    now = datetime.now(JST)
    settings = get_settings()
    rate_limit = settings.RATE_LIMIT_PER_MINUTE
    
    db = SessionLocal()
    try:
        created = process_new_events(db, now)
        if created > 0:
            logger.info(f"Created {created} new send_log reservations")
        
        email_service = get_email_service()
        pending = get_pending_send_logs(db, now, limit=rate_limit)
        
        sent_count = 0
        failed_count = 0
        
        for i, send_log in enumerate(pending):
            if i >= rate_limit:
                logger.info(f"Rate limit reached ({rate_limit}/min), deferring remaining to next tick")
                break
            
            success = send_single_email(db, send_log, email_service)
            if success:
                sent_count += 1
            else:
                failed_count += 1
            db.commit()
        
        if sent_count or failed_count:
            logger.info(f"Processed {sent_count} sent, {failed_count} failed")
        
        log_action(
            db=db,
            action="scheduler_tick",
            actor_id=None,
            actor_role_snapshot="system",
            target_type="system",
            target_id=None,
            details={
                "reservations_created": created,
                "sent": sent_count,
                "failed": failed_count
            }
        )
        db.commit()
        
    except Exception as e:
        logger.exception("Error in scheduler tick")
        db.rollback()
    finally:
        db.close()
    
    logger.info("Scheduler tick completed")
