"""Segment filtering service for scenario target leads"""
import json
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session
from email_validator import validate_email, EmailNotValidError

from src.ma_tool.models.lead import Lead
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.models.calendar_event import CalendarEvent
from src.ma_tool.models.lead_event_registration import LeadEventRegistration, RegistrationStatus


def apply_segment_conditions(
    query,
    scenario: Scenario
):
    """Apply segment conditions to a query that returns Lead objects.
    Returns the modified query with segment filters applied.
    """
    conditions = []
    
    if scenario.segment_graduation_year_from:
        conditions.append(Lead.graduation_year >= scenario.segment_graduation_year_from)
    
    if scenario.segment_graduation_year_to:
        conditions.append(Lead.graduation_year <= scenario.segment_graduation_year_to)
    
    
    if scenario.segment_school_name:
        conditions.append(Lead.school_name.ilike(f"%{scenario.segment_school_name}%"))
    
    if scenario.segment_tag:
        conditions.append(Lead.interest_tags.ilike(f"%{scenario.segment_tag}%"))
    
    if conditions:
        query = query.where(and_(*conditions))
    
    return query


def get_base_eligible_leads_query(db: Session, scenario: Optional[Scenario] = None):
    """Get base query for eligible leads (consent given, not unsubscribed, valid email)."""
    query = select(Lead).where(
        and_(
            Lead.consent == True,
            Lead.unsubscribed == False,
            Lead.email.isnot(None),
            Lead.email != ""
        )
    )
    return query


def is_valid_email(email: str) -> bool:
    """Check if email is valid."""
    if not email:
        return False
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def get_status_filter_list(scenario: Scenario) -> list:
    """Get the list of event statuses to filter by.
    Returns the configured statuses as RegistrationStatus enums or defaults to [SCHEDULED, ATTENDED].
    """
    default_statuses = [RegistrationStatus.SCHEDULED, RegistrationStatus.ATTENDED]
    
    if not scenario.segment_event_status_in:
        return default_statuses
    
    try:
        statuses = json.loads(scenario.segment_event_status_in)
        if isinstance(statuses, list) and statuses:
            result = []
            for s in statuses:
                try:
                    result.append(RegistrationStatus(s))
                except ValueError:
                    pass
            return result if result else default_statuses
    except (json.JSONDecodeError, TypeError):
        pass
    
    return default_statuses


def get_target_leads_for_scenario(
    db: Session,
    scenario: Scenario,
    calendar_event: Optional[CalendarEvent] = None,
    limit: Optional[int] = None
) -> Tuple[List[Lead], int]:
    """
    Get target leads for a scenario with all segment conditions applied.
    Returns (leads_list, total_count).
    
    This is the shared function used by both scheduler and preview.
    """
    query = get_base_eligible_leads_query(db, scenario)
    
    if scenario.base_date_type == "event_date" and calendar_event:
        status_list = get_status_filter_list(scenario)
        
        reg_stmt = select(LeadEventRegistration.lead_id).where(
            and_(
                LeadEventRegistration.calendar_event_id == calendar_event.id,
                LeadEventRegistration.status.in_(status_list)
            )
        )
        registered_lead_ids = [r for r in db.execute(reg_stmt).scalars().all()]
        
        if not registered_lead_ids:
            return [], 0
        
        query = query.where(Lead.id.in_(registered_lead_ids))
    
    query = apply_segment_conditions(query, scenario)
    
    if scenario.graduation_year_rule:
        try:
            rule = json.loads(scenario.graduation_year_rule)
            if "exact" in rule:
                query = query.where(Lead.graduation_year == rule["exact"])
            if "min" in rule:
                query = query.where(Lead.graduation_year >= rule["min"])
            if "max" in rule:
                query = query.where(Lead.graduation_year <= rule["max"])
            if "within_months" in rule:
                pass
        except (json.JSONDecodeError, TypeError):
            pass
    
    count_query = select(Lead.id).where(query.whereclause) if query.whereclause else select(Lead.id)
    total_count = len(list(db.execute(count_query).scalars().all()))
    
    if limit:
        query = query.limit(limit)
    
    leads = list(db.execute(query).scalars().all())
    
    leads = [l for l in leads if is_valid_email(l.email)]
    
    return leads, total_count


def get_scenario_preview(
    db: Session,
    scenario: Scenario,
    sample_limit: int = 10
) -> dict:
    """
    Get preview data for scenario targeting.
    Returns dict with count, sample leads, and condition summary.
    """
    calendar_event = None
    if scenario.base_date_type == "event_date":
        if scenario.target_calendar_event_id:
            calendar_event = db.get(CalendarEvent, scenario.target_calendar_event_id)
        elif scenario.event_type_filter:
            from datetime import date, timedelta
            today = date.today()
            event_query = select(CalendarEvent).where(
                and_(
                    CalendarEvent.is_active == True,
                    CalendarEvent.event_type == scenario.event_type_filter,
                    CalendarEvent.event_date >= today,
                    CalendarEvent.event_date <= today + timedelta(days=90)
                )
            ).order_by(CalendarEvent.event_date).limit(1)
            calendar_event = db.execute(event_query).scalar_one_or_none()
    
    leads, total_count = get_target_leads_for_scenario(
        db, scenario, calendar_event, limit=sample_limit
    )
    
    sample_leads = []
    for lead in leads[:sample_limit]:
        masked_email = mask_email(lead.email) if lead.email else "-"
        sample_leads.append({
            "name": lead.name or "名前なし",
            "email": masked_email,
            "graduation_year": lead.graduation_year,
            "school_name": lead.school_name,
        })
    
    condition_parts = []
    if scenario.trigger_event_type:
        condition_parts.append(f"トリガー={scenario.trigger_event_type}")
    if scenario.base_date_type == "event_date":
        if calendar_event:
            condition_parts.append(f"対象イベント={calendar_event.title}")
        elif scenario.event_type_filter:
            condition_parts.append(f"イベント種別={scenario.event_type_filter}")
    if scenario.segment_graduation_year_from or scenario.segment_graduation_year_to:
        from_y = scenario.segment_graduation_year_from or "〜"
        to_y = scenario.segment_graduation_year_to or "〜"
        condition_parts.append(f"卒業年度={from_y}〜{to_y}")
    if scenario.segment_grade_in:
        condition_parts.append(f"学年={scenario.segment_grade_in}")
    if scenario.segment_prefecture:
        condition_parts.append(f"都道府県={scenario.segment_prefecture}")
    if scenario.segment_school_name:
        condition_parts.append(f"高校={scenario.segment_school_name}")
    if scenario.segment_tag:
        condition_parts.append(f"タグ={scenario.segment_tag}")
    if scenario.segment_event_status_in and scenario.base_date_type == "event_date":
        try:
            statuses = json.loads(scenario.segment_event_status_in)
            status_labels = {"scheduled": "予定", "attended": "参加", "absent": "欠席", "cancelled": "キャンセル"}
            labels = [status_labels.get(s, s) for s in statuses]
            condition_parts.append(f"参加ステータス={','.join(labels)}")
        except (json.JSONDecodeError, TypeError):
            condition_parts.append(f"参加ステータス={scenario.segment_event_status_in}")
    
    return {
        "total_count": total_count,
        "sample_leads": sample_leads,
        "condition_summary": ", ".join(condition_parts) if condition_parts else "条件なし（全員対象）",
        "calendar_event": calendar_event,
    }


def mask_email(email: str) -> str:
    """Mask email for privacy (e.g., a***@example.com)"""
    if not email or "@" not in email:
        return email
    
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = local
    else:
        masked_local = local[0] + "***"
    
    return f"{masked_local}@{domain}"
