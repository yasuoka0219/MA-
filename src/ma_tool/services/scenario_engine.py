"""Scenario Engine - Rule evaluation and scheduling utilities"""
import json
from datetime import datetime, timedelta, date
from typing import Optional, Tuple, Dict, Any, List
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from src.ma_tool.models.lead import Lead
from src.ma_tool.models.event import Event
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.models.send_log import SendLog, SendStatus
from src.ma_tool.models.template import Template, TemplateStatus


JST = ZoneInfo("Asia/Tokyo")
SEND_WINDOW_START = 9
SEND_WINDOW_END = 20


def parse_graduation_year_rule(rule_json: Optional[str]) -> Optional[Dict[str, Any]]:
    if not rule_json:
        return None
    try:
        return json.loads(rule_json)
    except json.JSONDecodeError:
        return None


def check_graduation_year_rule(
    lead_graduation_year: int,
    rule: Optional[Dict[str, Any]],
    reference_date: Optional[date] = None
) -> bool:
    if rule is None:
        return True
    
    rule_type = rule.get("type")
    
    if rule_type == "in":
        allowed_years = rule.get("values", [])
        return lead_graduation_year in allowed_years
    
    elif rule_type == "within_months":
        months = rule.get("months", 12)
        ref = reference_date or date.today()
        
        if ref.month >= 4:
            current_academic_year = ref.year + 1
        else:
            current_academic_year = ref.year
        
        future_date = date(ref.year, ref.month, 1)
        total_months = future_date.month + months
        future_year = future_date.year + (total_months - 1) // 12
        future_month = ((total_months - 1) % 12) + 1
        
        if future_month >= 4:
            max_academic_year = future_year + 1
        else:
            max_academic_year = future_year
        
        return current_academic_year <= lead_graduation_year <= max_academic_year
    
    elif rule_type == "all":
        return True
    
    return True


def calculate_scheduled_for(
    event_date: datetime,
    delay_days: int
) -> datetime:
    scheduled = event_date + timedelta(days=delay_days)
    return scheduled


def adjust_to_send_window(dt: datetime) -> datetime:
    dt_jst = dt.astimezone(JST)
    hour = dt_jst.hour
    
    if hour < SEND_WINDOW_START:
        dt_jst = dt_jst.replace(hour=SEND_WINDOW_START, minute=0, second=0, microsecond=0)
    elif hour >= SEND_WINDOW_END:
        dt_jst = dt_jst + timedelta(days=1)
        dt_jst = dt_jst.replace(hour=SEND_WINDOW_START, minute=0, second=0, microsecond=0)
    
    return dt_jst


def check_frequency_limit(
    db: Session,
    lead_id: int,
    scenario_id: int,
    frequency_days: int,
    reference_time: datetime
) -> bool:
    cutoff = reference_time - timedelta(days=frequency_days)
    
    stmt = select(SendLog).where(
        and_(
            SendLog.lead_id == lead_id,
            SendLog.scenario_id == scenario_id,
            SendLog.status == SendStatus.SENT,
            SendLog.sent_at >= cutoff
        )
    )
    result = db.execute(stmt).first()
    return result is None


def check_duplicate_schedule(
    db: Session,
    lead_id: int,
    scenario_id: int,
    scheduled_for: datetime
) -> bool:
    stmt = select(SendLog).where(
        and_(
            SendLog.lead_id == lead_id,
            SendLog.scenario_id == scenario_id,
            SendLog.scheduled_for == scheduled_for
        )
    )
    result = db.execute(stmt).first()
    return result is None


def evaluate_scenario_for_lead(
    db: Session,
    scenario: Scenario,
    lead: Lead,
    event: Event,
    now: Optional[datetime] = None
) -> Tuple[bool, Optional[datetime], Optional[str]]:
    if now is None:
        now = datetime.now(JST)
    
    if not lead.consent:
        return False, None, "consent is false"
    
    if lead.unsubscribed:
        return False, None, "lead is unsubscribed"
    
    template = db.get(Template, scenario.template_id)
    if not template:
        return False, None, "template not found"
    
    if template.status != TemplateStatus.APPROVED or template.approved_at is None:
        return False, None, "template not approved"
    
    rule = parse_graduation_year_rule(scenario.graduation_year_rule)
    if not check_graduation_year_rule(lead.graduation_year, rule, event.event_date.date()):
        return False, None, "graduation_year_rule not matched"
    
    scheduled_for = calculate_scheduled_for(event.event_date, scenario.delay_days)
    scheduled_for = adjust_to_send_window(scheduled_for)
    
    if not check_frequency_limit(db, lead.id, scenario.id, scenario.frequency_days, scheduled_for):
        return False, None, f"frequency_days ({scenario.frequency_days}) not satisfied"
    
    if not check_duplicate_schedule(db, lead.id, scenario.id, scheduled_for):
        return False, None, "duplicate schedule exists"
    
    return True, scheduled_for, None


def find_matching_scenarios(db: Session, event_type: str) -> List[Scenario]:
    stmt = select(Scenario).where(
        and_(
            Scenario.trigger_event_type == event_type,
            Scenario.is_enabled == True
        )
    )
    return list(db.execute(stmt).scalars().all())


def create_send_log_reservation(
    db: Session,
    lead: Lead,
    scenario: Scenario,
    event: Event,
    scheduled_for: datetime
) -> Optional[SendLog]:
    send_log = SendLog(
        lead_id=lead.id,
        scenario_id=scenario.id,
        scheduled_for=scheduled_for,
        status=SendStatus.SCHEDULED,
        attempt_count=0
    )
    db.add(send_log)
    return send_log


def process_event_for_scenarios(
    db: Session,
    event: Event,
    now: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    results = []
    scenarios = find_matching_scenarios(db, event.type)
    lead = db.get(Lead, event.lead_id)
    
    if not lead:
        return results
    
    for scenario in scenarios:
        should_send, scheduled_for, reason = evaluate_scenario_for_lead(
            db, scenario, lead, event, now
        )
        
        result = {
            "scenario_id": scenario.id,
            "scenario_name": scenario.name,
            "lead_id": lead.id,
            "should_send": should_send,
            "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
            "skip_reason": reason
        }
        
        if should_send and scheduled_for:
            try:
                send_log = create_send_log_reservation(db, lead, scenario, event, scheduled_for)
                result["send_log_id"] = send_log.id if send_log else None
            except Exception as e:
                result["error"] = str(e)
                result["should_send"] = False
        
        results.append(result)
    
    return results
