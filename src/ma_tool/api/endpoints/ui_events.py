"""UI endpoints for calendar event management"""
import json
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_

from src.ma_tool.database import get_db
from src.ma_tool.models.calendar_event import CalendarEvent
from src.ma_tool.models.lead_event_registration import LeadEventRegistration, RegistrationStatus
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.models.audit_log import AuditLog
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings
from src.ma_tool.models.template import Template, TemplateStatus, ChannelType
from src.ma_tool.services.template_renderer import render_email_body, render_subject
from src.ma_tool.services.email import send_email

router = APIRouter(prefix="/ui", tags=["UI Events"])
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


EVENT_TYPE_OPTIONS = [
    ("oc", "オープンキャンパス"),
    ("briefing", "説明会"),
    ("interview", "面談"),
    ("tour", "見学会"),
    ("other", "その他"),
]


@router.get("/events", response_class=HTMLResponse)
async def events_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    status_filter: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None),
):
    query = select(CalendarEvent)
    
    if status_filter == "active":
        query = query.where(CalendarEvent.is_active == True)
    elif status_filter == "inactive":
        query = query.where(CalendarEvent.is_active == False)
    
    if type_filter:
        query = query.where(CalendarEvent.event_type == type_filter)
    
    query = query.order_by(CalendarEvent.event_date.desc())
    event_list = db.execute(query).scalars().all()
    
    reg_counts = {}
    if event_list:
        event_ids = [e.id for e in event_list]
        counts = db.execute(
            select(
                LeadEventRegistration.calendar_event_id,
                func.count(LeadEventRegistration.id)
            ).where(LeadEventRegistration.calendar_event_id.in_(event_ids))
            .group_by(LeadEventRegistration.calendar_event_id)
        ).all()
        reg_counts = {row[0]: row[1] for row in counts}
    
    return templates.TemplateResponse("ui_events_list.html", {
        **get_base_context(request, user),
        "events": event_list,
        "reg_counts": reg_counts,
        "status_filter": status_filter or "",
        "type_filter": type_filter or "",
        "event_types": EVENT_TYPE_OPTIONS,
        "can_edit": can_edit(user),
    })


@router.get("/events/new", response_class=HTMLResponse)
async def event_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/events", status_code=302)
    
    return templates.TemplateResponse("ui_event_form.html", {
        **get_base_context(request, user),
        "event": None,
        "is_new": True,
        "event_types": EVENT_TYPE_OPTIONS,
        "can_edit": True,
    })


@router.post("/events/new", response_class=HTMLResponse)
async def event_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    event_type: str = Form(...),
    title: str = Form(...),
    event_date: str = Form(...),
    location: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    is_active: bool = Form(True),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/events", status_code=302)
    
    try:
        parsed_date = datetime.strptime(event_date, "%Y-%m-%d").date()
    except ValueError:
        return templates.TemplateResponse("ui_event_form.html", {
            **get_base_context(request, user),
            "event": None,
            "is_new": True,
            "event_types": EVENT_TYPE_OPTIONS,
            "can_edit": True,
            "error": "日付形式が不正です",
        })
    
    new_event = CalendarEvent(
        event_type=event_type,
        title=title,
        event_date=parsed_date,
        location=location or None,
        notes=notes or None,
        is_active=is_active,
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    
    create_audit_log(db, user, "create", "calendar_event", new_event.id, {"title": title})
    
    response = RedirectResponse(url=f"/ui/events/{new_event.id}", status_code=302)
    return response


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def event_detail(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    search: Optional[str] = Query(None),
    grad_year: Optional[str] = Query(None),
    consent_only: Optional[str] = Query(None),
):
    event = db.get(CalendarEvent, event_id)
    if not event:
        return RedirectResponse(url="/ui/events", status_code=302)
    
    registrations = db.execute(
        select(LeadEventRegistration)
        .where(LeadEventRegistration.calendar_event_id == event_id)
        .order_by(LeadEventRegistration.created_at.desc())
    ).scalars().all()
    
    lead_ids = [r.lead_id for r in registrations]
    leads_map = {}
    if lead_ids:
        leads = db.execute(select(Lead).where(Lead.id.in_(lead_ids))).scalars().all()
        leads_map = {l.id: l for l in leads}
    
    available_years = db.execute(
        select(Lead.graduation_year)
        .where(Lead.graduation_year.isnot(None))
        .distinct()
        .order_by(Lead.graduation_year.desc())
    ).scalars().all()
    
    search_results = []
    has_filter = search or grad_year
    if has_filter:
        query = select(Lead)
        conditions = []
        
        if search:
            conditions.append(
                or_(
                    Lead.name.ilike(f"%{search}%"),
                    Lead.email.ilike(f"%{search}%"),
                    Lead.external_id.ilike(f"%{search}%") if hasattr(Lead, 'external_id') else False
                )
            )
        
        if grad_year:
            try:
                conditions.append(Lead.graduation_year == int(grad_year))
            except ValueError:
                pass
        
        if consent_only:
            conditions.append(Lead.consent_given == True)
            conditions.append(Lead.unsubscribed == False)
        
        if conditions:
            from sqlalchemy import and_
            query = query.where(and_(*conditions))
        
        query = query.order_by(Lead.graduation_year.desc(), Lead.name).limit(100)
        search_results = db.execute(query).scalars().all()
        search_results = [l for l in search_results if l.id not in lead_ids]
    
    approved_templates = db.execute(
        select(Template).where(
            Template.status == TemplateStatus.APPROVED,
            Template.channel_type == ChannelType.EMAIL,
        )
    ).scalars().all()
    
    return templates.TemplateResponse("ui_event_detail.html", {
        **get_base_context(request, user),
        "event": event,
        "registrations": registrations,
        "leads_map": leads_map,
        "search": search or "",
        "grad_year": grad_year or "",
        "consent_only": bool(consent_only),
        "available_years": available_years,
        "search_results": search_results,
        "event_types": EVENT_TYPE_OPTIONS,
        "status_options": [
            (RegistrationStatus.SCHEDULED, "参加予定"),
            (RegistrationStatus.ATTENDED, "参加済"),
            (RegistrationStatus.ABSENT, "欠席"),
            (RegistrationStatus.CANCELLED, "キャンセル"),
        ],
        "can_edit": can_edit(user),
        "approved_templates": approved_templates,
    })


@router.get("/events/{event_id}/edit", response_class=HTMLResponse)
async def event_edit(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    event = db.get(CalendarEvent, event_id)
    if not event:
        return RedirectResponse(url="/ui/events", status_code=302)
    
    return templates.TemplateResponse("ui_event_form.html", {
        **get_base_context(request, user),
        "event": event,
        "is_new": False,
        "event_types": EVENT_TYPE_OPTIONS,
        "can_edit": True,
    })


@router.post("/events/{event_id}/edit", response_class=HTMLResponse)
async def event_update(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    event_type: str = Form(...),
    title: str = Form(...),
    event_date: str = Form(...),
    location: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    is_active: bool = Form(False),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    event = db.get(CalendarEvent, event_id)
    if not event:
        return RedirectResponse(url="/ui/events", status_code=302)
    
    try:
        parsed_date = datetime.strptime(event_date, "%Y-%m-%d").date()
    except ValueError:
        return templates.TemplateResponse("ui_event_form.html", {
            **get_base_context(request, user),
            "event": event,
            "is_new": False,
            "event_types": EVENT_TYPE_OPTIONS,
            "can_edit": True,
            "error": "日付形式が不正です",
        })
    
    event.event_type = event_type
    event.title = title
    event.event_date = parsed_date
    event.location = location or None
    event.notes = notes or None
    event.is_active = is_active
    db.commit()
    
    create_audit_log(db, user, "update", "calendar_event", event_id, {"title": title})
    
    return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)


@router.post("/events/{event_id}/toggle-active")
async def event_toggle_active(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/events", status_code=302)
    
    event = db.get(CalendarEvent, event_id)
    if event:
        event.is_active = not event.is_active
        db.commit()
        create_audit_log(db, user, "toggle_active", "calendar_event", event_id, {"is_active": event.is_active})
    
    return RedirectResponse(url="/ui/events", status_code=302)


@router.post("/events/{event_id}/registrations/add")
async def add_registration(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    lead_id: int = Form(...),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    event = db.get(CalendarEvent, event_id)
    lead = db.get(Lead, lead_id)
    
    if not event or not lead:
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    existing = db.execute(
        select(LeadEventRegistration)
        .where(
            LeadEventRegistration.calendar_event_id == event_id,
            LeadEventRegistration.lead_id == lead_id
        )
    ).scalar_one_or_none()
    
    if not existing:
        reg = LeadEventRegistration(
            lead_id=lead_id,
            calendar_event_id=event_id,
            status=RegistrationStatus.SCHEDULED,
        )
        db.add(reg)
        db.commit()
        create_audit_log(db, user, "add_registration", "calendar_event", event_id, {"lead_id": lead_id})
    
    return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)


@router.post("/events/{event_id}/registrations/bulk-add")
async def bulk_add_registrations(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    lead_ids: str = Form(...),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    event = db.get(CalendarEvent, event_id)
    if not event:
        return RedirectResponse(url="/ui/events", status_code=302)
    
    added_count = 0
    for lead_id_str in lead_ids.split(","):
        try:
            lead_id = int(lead_id_str.strip())
        except ValueError:
            continue
        
        lead = db.get(Lead, lead_id)
        if not lead:
            continue
        
        existing = db.execute(
            select(LeadEventRegistration)
            .where(
                LeadEventRegistration.calendar_event_id == event_id,
                LeadEventRegistration.lead_id == lead_id
            )
        ).scalar_one_or_none()
        
        if not existing:
            reg = LeadEventRegistration(
                lead_id=lead_id,
                calendar_event_id=event_id,
                status=RegistrationStatus.SCHEDULED,
            )
            db.add(reg)
            added_count += 1
    
    db.commit()
    
    if added_count > 0:
        create_audit_log(db, user, "bulk_add_registration", "calendar_event", event_id, {"count": added_count})
    
    return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)


@router.post("/events/{event_id}/registrations/{reg_id}/remove")
async def remove_registration(
    event_id: int,
    reg_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    reg = db.get(LeadEventRegistration, reg_id)
    if reg and reg.calendar_event_id == event_id:
        lead_id = reg.lead_id
        db.delete(reg)
        db.commit()
        create_audit_log(db, user, "remove_registration", "calendar_event", event_id, {"lead_id": lead_id})
    
    return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)


@router.post("/events/{event_id}/registrations/{reg_id}/status")
async def update_registration_status(
    event_id: int,
    reg_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    status: str = Form(...),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    reg = db.get(LeadEventRegistration, reg_id)
    if reg and reg.calendar_event_id == event_id:
        reg.status = status
        db.commit()
        create_audit_log(db, user, "update_registration_status", "calendar_event", event_id, {"reg_id": reg_id, "status": status})
    
    return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)


@router.post("/events/{event_id}/send-emails")
async def event_send_emails(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    template_id: int = Form(...),
    selected_lead_ids: str = Form(...),
):
    """イベント参加者に対する一括メール送信（UIからの手動送信）"""
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/events/{event_id}", status_code=302)
    
    event = db.get(CalendarEvent, event_id)
    if not event:
        return RedirectResponse(url="/ui/events", status_code=302)
    
    selected_lead_ids = (selected_lead_ids or "").strip()
    if not selected_lead_ids:
        return RedirectResponse(
            url=f"/ui/events/{event_id}?message=送信対象が選択されていません",
            status_code=302,
        )
    
    try:
        lead_ids = [int(x.strip()) for x in selected_lead_ids.split(",") if x.strip()]
    except ValueError:
        return RedirectResponse(
            url=f"/ui/events/{event_id}?message=送信対象のIDが不正です",
            status_code=302,
        )
    
    if not lead_ids:
        return RedirectResponse(
            url=f"/ui/events/{event_id}?message=送信対象が選択されていません",
            status_code=302,
        )
    
    template = db.get(Template, template_id)
    if not template:
        return RedirectResponse(
            url=f"/ui/events/{event_id}?message=テンプレートが見つかりません",
            status_code=302,
        )
    
    if template.status != TemplateStatus.APPROVED or template.channel_type != ChannelType.EMAIL:
        return RedirectResponse(
            url=f"/ui/events/{event_id}?message=承認済みのメールテンプレートのみ送信できます",
            status_code=302,
        )
    
    leads = db.execute(select(Lead).where(Lead.id.in_(lead_ids))).scalars().all()
    leads_map = {l.id: l for l in leads}
    
    sent_count = 0
    skipped_count = 0
    
    for lead_id in lead_ids:
        lead = leads_map.get(lead_id)
        if not lead:
            skipped_count += 1
            continue
        
        # 配信許諾と配信停止、メールアドレスの有無を確認
        if not lead.consent or lead.unsubscribed or not lead.email:
            skipped_count += 1
            continue
        
        try:
            body = render_email_body(template.body_html or "", lead)
            subject = render_subject(template.subject or "", lead)
            result = send_email(
                to_email=lead.email,
                subject=subject or "",
                html_content=body,
            )
            if result.success:
                sent_count += 1
            else:
                skipped_count += 1
        except Exception:
            skipped_count += 1
    
    # 監査ログに記録
    meta = {
        "template_id": template.id,
        "lead_ids": lead_ids,
        "sent_count": sent_count,
        "skipped_count": skipped_count,
    }
    create_audit_log(db, user, "send_emails", "calendar_event", event_id, meta)
    
    message = f"{sent_count}件のメールを送信しました"
    if skipped_count:
        message += f"（{skipped_count}件は送信対象外またはエラー）"
    
    return RedirectResponse(
        url=f"/ui/events/{event_id}?message={message}",
        status_code=302,
    )
