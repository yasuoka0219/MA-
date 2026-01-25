"""UI endpoints for scenario management"""
import json
from datetime import datetime, timezone
from typing import Optional, List
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
from src.ma_tool.services.segment_filter import get_scenario_preview

CALENDAR_EVENT_TYPES = [
    ("oc", "オープンキャンパス"),
    ("briefing", "説明会"),
    ("interview", "面談"),
    ("tour", "見学会"),
    ("other", "その他"),
]

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]


def get_available_years(db: Session) -> List[int]:
    years = db.execute(
        select(Lead.graduation_year)
        .where(Lead.graduation_year.isnot(None))
        .distinct()
        .order_by(Lead.graduation_year.desc())
    ).scalars().all()
    current_year = datetime.now().year
    all_years = set(years) | {current_year + i for i in range(5)}
    return sorted(all_years, reverse=True)

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
        "available_years": get_available_years(db),
        "prefectures": PREFECTURES,
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
    segment_graduation_year_from: Optional[int] = Form(None),
    segment_graduation_year_to: Optional[int] = Form(None),
    segment_grade_in: Optional[List[str]] = Form(None),
    segment_prefecture: Optional[str] = Form(None),
    segment_school_name: Optional[str] = Form(None),
    segment_tag: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/scenarios", status_code=302)
    
    grade_in_json = json.dumps(segment_grade_in) if segment_grade_in else None
    
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
        segment_graduation_year_from=segment_graduation_year_from or None,
        segment_graduation_year_to=segment_graduation_year_to or None,
        segment_grade_in=grade_in_json,
        segment_prefecture=segment_prefecture or None,
        segment_school_name=segment_school_name or None,
        segment_tag=segment_tag or None,
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
        "available_years": get_available_years(db),
        "prefectures": PREFECTURES,
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
    segment_graduation_year_from: Optional[int] = Form(None),
    segment_graduation_year_to: Optional[int] = Form(None),
    segment_grade_in: Optional[List[str]] = Form(None),
    segment_prefecture: Optional[str] = Form(None),
    segment_school_name: Optional[str] = Form(None),
    segment_tag: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/scenarios/{scenario_id}", status_code=302)
    
    scenario = db.execute(select(Scenario).where(Scenario.id == scenario_id)).scalar_one_or_none()
    if not scenario:
        return RedirectResponse(url="/ui/scenarios", status_code=302)
    
    old_enabled = scenario.is_enabled
    grade_in_json = json.dumps(segment_grade_in) if segment_grade_in else None
    
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
    scenario.segment_graduation_year_from = segment_graduation_year_from or None
    scenario.segment_graduation_year_to = segment_graduation_year_to or None
    scenario.segment_grade_in = grade_in_json
    scenario.segment_prefecture = segment_prefecture or None
    scenario.segment_school_name = segment_school_name or None
    scenario.segment_tag = segment_tag or None
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
    
    preview_data = get_scenario_preview(db, scenario, sample_limit=10)
    
    return templates.TemplateResponse("ui_scenario_preview.html", {
        **get_base_context(request, user),
        "scenario": scenario,
        "preview": preview_data,
    })
