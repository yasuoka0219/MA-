"""APScheduler-based scenario runner with rate limiting and retry"""
import logging
from datetime import datetime, timedelta, date
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_, update, or_
from sqlalchemy.orm import Session

from src.ma_tool.database import SessionLocal
from src.ma_tool.models.send_log import SendLog, SendStatus
from src.ma_tool.models.scenario import Scenario, BaseDateType
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.template import Template
from src.ma_tool.models.event import Event
from src.ma_tool.models.calendar_event import CalendarEvent
from src.ma_tool.models.lead_event_registration import LeadEventRegistration, RegistrationStatus
from src.ma_tool.services.email import EmailService, EmailMessage, get_email_service
from src.ma_tool.services.audit import log_action
from sqlalchemy.exc import IntegrityError
from src.ma_tool.services.scenario_engine import (
    find_matching_scenarios,
    evaluate_scenario_for_lead,
    create_send_log_reservation,
)
from src.ma_tool.services.template_renderer import render_email_body, render_subject
from src.ma_tool.services.segment_filter import apply_segment_conditions, is_valid_email, get_status_filter_list
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


def process_event_date_scenarios(db: Session, now: Optional[datetime] = None) -> int:
    """Process scenarios based on event_date (calendar event date)."""
    if now is None:
        now = datetime.now(JST)
    
    today = now.date()
    
    stmt = select(Scenario).where(
        and_(
            Scenario.is_enabled == True,
            Scenario.base_date_type == BaseDateType.EVENT_DATE
        )
    )
    scenarios = list(db.execute(stmt).scalars().all())
    
    created_count = 0
    for scenario in scenarios:
        event_query = select(CalendarEvent).where(
            and_(
                CalendarEvent.is_active == True,
                CalendarEvent.event_date >= today - timedelta(days=30),
                CalendarEvent.event_date <= today + timedelta(days=90)
            )
        )
        
        if scenario.target_calendar_event_id:
            event_query = event_query.where(CalendarEvent.id == scenario.target_calendar_event_id)
        elif scenario.event_type_filter:
            event_query = event_query.where(CalendarEvent.event_type == scenario.event_type_filter)
        
        calendar_events = list(db.execute(event_query).scalars().all())
        
        for cal_event in calendar_events:
            send_date = cal_event.event_date + timedelta(days=scenario.delay_days)
            
            if send_date > today:
                continue
            if send_date < today - timedelta(days=1):
                continue
            
            status_list = get_status_filter_list(scenario)
            
            reg_stmt = select(LeadEventRegistration).where(
                and_(
                    LeadEventRegistration.calendar_event_id == cal_event.id,
                    LeadEventRegistration.status.in_(status_list)
                )
            )
            registrations = list(db.execute(reg_stmt).scalars().all())
            
            lead_ids = [reg.lead_id for reg in registrations]
            if not lead_ids:
                continue
            
            lead_query = select(Lead).where(
                and_(
                    Lead.id.in_(lead_ids),
                    Lead.consent == True,
                    Lead.unsubscribed == False,
                    Lead.email.isnot(None),
                    Lead.email != ""
                )
            )
            
            lead_query = apply_segment_conditions(lead_query, scenario)
            
            if scenario.graduation_year_rule:
                import json
                try:
                    rule = json.loads(scenario.graduation_year_rule)
                    if "exact" in rule:
                        lead_query = lead_query.where(Lead.graduation_year == rule["exact"])
                    if "min" in rule:
                        lead_query = lead_query.where(Lead.graduation_year >= rule["min"])
                    if "max" in rule:
                        lead_query = lead_query.where(Lead.graduation_year <= rule["max"])
                except:
                    pass
            
            eligible_leads = list(db.execute(lead_query).scalars().all())
            eligible_leads = [lead for lead in eligible_leads if is_valid_email(lead.email)]
            
            for lead in eligible_leads:
                scheduled_for = datetime.combine(send_date, datetime.min.time().replace(hour=9))
                scheduled_for = scheduled_for.replace(tzinfo=JST)
                
                settings = get_settings()
                existing = db.execute(
                    select(SendLog).where(
                        and_(
                            SendLog.lead_id == lead.id,
                            SendLog.scenario_id == scenario.id,
                            SendLog.calendar_event_id == cal_event.id
                        )
                    )
                ).scalar_one_or_none()
                
                if existing:
                    continue
                
                try:
                    send_log = SendLog(
                        lead_id=lead.id,
                        scenario_id=scenario.id,
                        calendar_event_id=cal_event.id,
                        status=SendStatus.SCHEDULED,
                        scheduled_for=scheduled_for,
                        channel="email"
                    )
                    db.add(send_log)
                    db.commit()
                    created_count += 1
                    
                    log_action(
                        db=db,
                        action="send_log_reserved_event_based",
                        actor_id=None,
                        actor_role_snapshot="system",
                        target_type="send_log",
                        target_id=send_log.id,
                        details={
                            "lead_id": lead.id,
                            "scenario_id": scenario.id,
                            "calendar_event_id": cal_event.id,
                            "scheduled_for": scheduled_for.isoformat()
                        }
                    )
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.debug(f"Skipping duplicate: lead={lead.id}, scenario={scenario.id}, event={cal_event.id}")
                except Exception as e:
                    db.rollback()
                    logger.warning(f"Error creating event-based send_log: {e}")
    
    return created_count


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
            logger.info(f"Created {created} new send_log reservations (lead_created_at based)")
        
        event_created = process_event_date_scenarios(db, now)
        if event_created > 0:
            logger.info(f"Created {event_created} new send_log reservations (event_date based)")
        
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
                "event_reservations_created": event_created,
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
