"""UI endpoints for scenario management"""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import get_db
from src.ma_tool.models.scenario import Scenario, BaseDateType
from src.ma_tool.models.template import Template, TemplateStatus, ChannelType
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.event import Event
from src.ma_tool.models.calendar_event import CalendarEvent
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.models.audit_log import AuditLog
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings

CALENDAR_EVENT_TYPES = [
    ("oc", "オープンキャンパス"),
    ("briefing", "説明会"),
    ("interview", "面談"),
    ("tour", "見学会"),
    ("other", "その他"),
]

router = APIRouter(prefix="/ui", tags=["UI Scenarios"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


def create_audit_log(db: Session, user: User, action: str, target_type: str, target_id: int, meta: Optional[dict] = None):
    log = AuditLog(
        actor_user_id=user.id,
        actor_role_snapshot=user.role.value,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta_json=json.dumps(meta) if meta else None,
    )
    db.add(log)
    db.commit()


def can_edit(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.EDITOR]


@router.get("/scenarios", response_class=HTMLResponse)
async def scenarios_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    enabled_filter: Optional[str] = Query(None),
):
    query = select(Scenario)
    
    if enabled_filter == "enabled":
        query = query.where(Scenario.is_enabled == True)
    elif enabled_filter == "disabled":
        query = query.where(Scenario.is_enabled == False)
    
    query = query.order_by(Scenario.created_at.desc())
    scenario_list = db.execute(query).scalars().all()
    
    template_ids = [s.template_id for s in scenario_list]
    tmpl_map = {}
    if template_ids:
        tmpls = db.execute(select(Template).where(Template.id.in_(template_ids))).scalars().all()
        tmpl_map = {t.id: t for t in tmpls}
    
    return templates.TemplateResponse("ui_scenarios_list.html", {
        **get_base_context(request, user),
        "scenarios": scenario_list,
        "templates": tmpl_map,
        "enabled_filter": enabled_filter or "",
        "can_edit": can_edit(user),
    })


@router.get("/scenarios/new", response_class=HTMLResponse)
async def scenario_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/scenarios", status_code=302)
    
    approved_templates = db.execute(
        select(Template).where(Template.status == TemplateStatus.APPROVED)
    ).scalars().all()
    
    event_types = db.execute(
        select(Event.type).distinct()
    ).scalars().all()
    
    calendar_events = db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.is_active == True)
        .order_by(CalendarEvent.event_date.desc())
    ).scalars().all()
    
    return templates.TemplateResponse("ui_scenario_form.html", {
        **get_base_context(request, user),
        "scenario": None,
        "is_new": True,
        "approved_templates": approved_templates,
        "event_types": event_types,
        "calendar_event_types": CALENDAR_EVENT_TYPES,
        "calendar_events": calendar_events,
    })


@router.post("/scenarios/new")
async def scenario_create(
    request: Request,
    name: str = Form(...),
    template_id: int = Form(...),
    trigger_event_type: str = Form(...),
    delay_days: int = Form(0),
    frequency_days: int = Form(7),
    graduation_year_rule: Optional[str] = Form(None),
    is_enabled: bool = Form(False),
    base_date_type: str = Form(BaseDateType.LEAD_CREATED_AT),
    event_type_filter: Optional[str] = Form(None),
    target_calendar_event_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/scenarios", status_code=302)
    
    scenario = Scenario(
        name=name,
        template_id=template_id,
        trigger_event_type=trigger_event_type,
        delay_days=delay_days,
        frequency_days=frequency_days,
        graduation_year_rule=graduation_year_rule,
        is_enabled=is_enabled and not settings.is_production,
        base_date_type=base_date_type,
        event_type_filter=event_type_filter or None,
        target_calendar_event_id=target_calendar_event_id or None,
    )
    db.add(scenario)
    db.commit()
    
    create_audit_log(db, user, "create", "scenario", scenario.id, {"name": name})
    
    return RedirectResponse(url=f"/ui/scenarios/{scenario.id}", status_code=302)


@router.get("/scenarios/{scenario_id}", response_class=HTMLResponse)
async def scenario_detail(
    request: Request,
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    scenario = db.execute(select(Scenario).where(Scenario.id == scenario_id)).scalar_one_or_none()
    if not scenario:
        return HTMLResponse("<h1>シナリオが見つかりません</h1>", status_code=404)
    
    template = db.execute(select(Template).where(Template.id == scenario.template_id)).scalar_one_or_none()
    
    approved_templates = db.execute(
        select(Template).where(Template.status == TemplateStatus.APPROVED)
    ).scalars().all()
    
    event_types = db.execute(
        select(Event.type).distinct()
    ).scalars().all()
    
    calendar_events = db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.is_active == True)
        .order_by(CalendarEvent.event_date.desc())
    ).scalars().all()
    
    return templates.TemplateResponse("ui_scenario_form.html", {
        **get_base_context(request, user),
        "scenario": scenario,
        "template": template,
        "is_new": False,
        "approved_templates": approved_templates,
        "event_types": event_types,
        "calendar_event_types": CALENDAR_EVENT_TYPES,
        "calendar_events": calendar_events,
        "can_edit": can_edit(user),
    })


@router.post("/scenarios/{scenario_id}")
async def scenario_update(
    request: Request,
    scenario_id: int,
    name: str = Form(...),
    template_id: int = Form(...),
    trigger_event_type: str = Form(...),
    delay_days: int = Form(0),
    frequency_days: int = Form(7),
    graduation_year_rule: Optional[str] = Form(None),
    is_enabled: bool = Form(False),
    base_date_type: str = Form(BaseDateType.LEAD_CREATED_AT),
    event_type_filter: Optional[str] = Form(None),
    target_calendar_event_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/scenarios/{scenario_id}", status_code=302)
    
    scenario = db.execute(select(Scenario).where(Scenario.id == scenario_id)).scalar_one_or_none()
    if not scenario:
        return RedirectResponse(url="/ui/scenarios", status_code=302)
    
    old_enabled = scenario.is_enabled
    
    scenario.name = name
    scenario.template_id = template_id
    scenario.trigger_event_type = trigger_event_type
    scenario.delay_days = delay_days
    scenario.frequency_days = frequency_days
    scenario.graduation_year_rule = graduation_year_rule or ""
    scenario.is_enabled = is_enabled
    scenario.base_date_type = base_date_type
    scenario.event_type_filter = event_type_filter or None
    scenario.target_calendar_event_id = target_calendar_event_id or None
    scenario.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    if old_enabled != is_enabled:
        action = "enable" if is_enabled else "disable"
        create_audit_log(db, user, action, "scenario", scenario_id)
    else:
        create_audit_log(db, user, "update", "scenario", scenario_id)
    
    return RedirectResponse(url=f"/ui/scenarios/{scenario_id}", status_code=302)


@router.post("/scenarios/{scenario_id}/toggle", response_class=HTMLResponse)
async def scenario_toggle(
    request: Request,
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return Response(content="<span class='text-danger'>権限不足</span>", media_type="text/html")
    
    scenario = db.execute(select(Scenario).where(Scenario.id == scenario_id)).scalar_one_or_none()
    if not scenario:
        return Response(content="<span class='text-danger'>不明</span>", media_type="text/html")
    
    scenario.is_enabled = not scenario.is_enabled
    db.commit()
    
    action = "enable" if scenario.is_enabled else "disable"
    create_audit_log(db, user, action, "scenario", scenario_id)
    
    if scenario.is_enabled:
        content = '<span class="badge bg-success">有効</span>'
        msg = "シナリオを有効化しました"
    else:
        content = '<span class="badge bg-secondary">無効</span>'
        msg = "シナリオを無効化しました"
    
    response = Response(content=content, media_type="text/html")
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "success"}})
    return response


@router.post("/scenarios/{scenario_id}/preview", response_class=HTMLResponse)
async def scenario_preview(
    request: Request,
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    scenario = db.execute(select(Scenario).where(Scenario.id == scenario_id)).scalar_one_or_none()
    if not scenario:
        return Response(content="<div class='alert alert-danger'>シナリオが見つかりません</div>", media_type="text/html")
    
    query = select(Lead).where(
        Lead.consent == True,
        Lead.unsubscribed == False,
    )
    
    if scenario.graduation_year_rule:
        try:
            rule = json.loads(scenario.graduation_year_rule)
            if "exact" in rule:
                query = query.where(Lead.graduation_year == rule["exact"])
            elif "min" in rule or "max" in rule:
                if "min" in rule:
                    query = query.where(Lead.graduation_year >= rule["min"])
                if "max" in rule:
                    query = query.where(Lead.graduation_year <= rule["max"])
        except json.JSONDecodeError:
            pass
    
    leads = db.execute(query.limit(20)).scalars().all()
    total_count = db.execute(query).scalars().all().__len__()
    
    return templates.TemplateResponse("ui_scenario_preview.html", {
        **get_base_context(request, user),
        "scenario": scenario,
        "leads": leads,
        "total_count": total_count,
    })
