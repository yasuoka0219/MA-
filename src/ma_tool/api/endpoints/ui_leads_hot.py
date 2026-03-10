"""UI endpoints for hot leads (engagement scoring)"""
import math
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, and_

from src.ma_tool.database import get_db
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.engagement_event import EngagementEvent
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings
from src.ma_tool.models.template import Template, TemplateStatus, ChannelType
from src.ma_tool.services.template_renderer import render_email_body, render_subject
from src.ma_tool.services.email import send_email
from src.ma_tool.services.audit import log_action

router = APIRouter(prefix="/ui", tags=["UI Hot Leads"])
templates = Jinja2Templates(directory="src/ma_tool/templates")

JST = ZoneInfo("Asia/Tokyo")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


def can_edit(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.EDITOR]


@router.get("/leads/hot", response_class=HTMLResponse)
async def leads_hot(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    band: Optional[str] = Query(None),
    graduation_year: Optional[int] = Query(None),
    days: Optional[int] = Query(None),
    min_pv: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    per_page = 50
    now = datetime.now(JST)

    query = select(Lead).where(Lead.engagement_score > 0)

    if band:
        query = query.where(Lead.score_band == band)
    if graduation_year:
        query = query.where(Lead.graduation_year == graduation_year)
    if days:
        cutoff = now - timedelta(days=days)
        query = query.where(Lead.last_engaged_at >= cutoff)
    if search:
        query = query.where(
            or_(
                Lead.name.ilike(f"%{search}%"),
                Lead.email.ilike(f"%{search}%"),
            )
        )

    if min_pv:
        seven_days_ago = now - timedelta(days=7)
        pv_subq = (
            select(EngagementEvent.lead_id)
            .where(
                and_(
                    EngagementEvent.event_type == "page_view",
                    EngagementEvent.occurred_at >= seven_days_ago,
                    EngagementEvent.lead_id.isnot(None),
                )
            )
            .group_by(EngagementEvent.lead_id)
            .having(func.count() >= min_pv)
        ).subquery()
        query = query.where(Lead.id.in_(select(pv_subq.c.lead_id)))

    total_count = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    offset = (page - 1) * per_page

    leads = db.execute(
        query.order_by(Lead.engagement_score.desc(), Lead.last_engaged_at.desc())
        .offset(offset).limit(per_page)
    ).scalars().all()

    seven_days_ago = now - timedelta(days=7)
    leads_data = []
    for lead in leads:
        last_click = db.execute(
            select(EngagementEvent.url)
            .where(
                and_(
                    EngagementEvent.lead_id == lead.id,
                    EngagementEvent.event_type == "click",
                )
            )
            .order_by(EngagementEvent.occurred_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        pv_7d = db.execute(
            select(func.count())
            .select_from(EngagementEvent)
            .where(
                and_(
                    EngagementEvent.lead_id == lead.id,
                    EngagementEvent.event_type == "page_view",
                    EngagementEvent.occurred_at >= seven_days_ago,
                )
            )
        ).scalar() or 0

        leads_data.append({
            "lead": lead,
            "last_click_url": last_click,
            "pv_7d": pv_7d,
        })

    hot_count = db.execute(select(func.count()).select_from(Lead).where(Lead.score_band == "hot")).scalar() or 0
    warm_count = db.execute(select(func.count()).select_from(Lead).where(Lead.score_band == "warm")).scalar() or 0
    cold_count = db.execute(select(func.count()).select_from(Lead).where(Lead.score_band == "cold")).scalar() or 0

    graduation_years = db.execute(
        select(Lead.graduation_year).distinct()
        .where(Lead.graduation_year.isnot(None))
        .order_by(Lead.graduation_year.desc())
    ).scalars().all()

    approved_templates = db.execute(
        select(Template).where(
            Template.channel_type == ChannelType.EMAIL,
            Template.status == TemplateStatus.APPROVED,
        )
    ).scalars().all()

    return templates.TemplateResponse("ui_leads_hot.html", {
        **get_base_context(request, user),
        "leads_data": leads_data,
        "total_count": total_count,
        "total_pages": total_pages,
        "per_page": per_page,
        "page": page,
        "band": band or "",
        "graduation_year": graduation_year,
        "graduation_years": graduation_years,
        "days": days,
        "min_pv": min_pv,
        "search": search or "",
        "hot_count": hot_count,
        "warm_count": warm_count,
        "cold_count": cold_count,
        "approved_templates": approved_templates,
        "can_edit": can_edit(user),
    })


@router.post("/leads/hot/bulk-email")
async def leads_hot_bulk_email(
    request: Request,
    template_id: int = Form(...),
    lead_ids: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """高温度リード一覧からの一括メール送信（admin/editorのみ）"""
    if not can_edit(user):
        response = RedirectResponse(url="/ui/leads/hot?error=メール送信の権限がありません", status_code=302)
        return response

    lead_ids = (lead_ids or "").strip()
    if not lead_ids:
        response = RedirectResponse(url="/ui/leads/hot?error=送信対象が選択されていません", status_code=302)
        return response

    try:
        ids = [int(id_str.strip()) for id_str in lead_ids.split(",") if id_str.strip()]
    except ValueError:
        response = RedirectResponse(url="/ui/leads/hot?error=送信対象のIDが不正です", status_code=302)
        return response

    if not ids:
        response = RedirectResponse(url="/ui/leads/hot?error=送信対象が選択されていません", status_code=302)
        return response

    template = db.get(Template, template_id)
    if not template:
        response = RedirectResponse(url="/ui/leads/hot?error=テンプレートが見つかりません", status_code=302)
        return response

    if template.status != TemplateStatus.APPROVED or template.channel_type != ChannelType.EMAIL:
        response = RedirectResponse(
            url="/ui/leads/hot?error=承認済みのメールテンプレートのみ送信できます", status_code=302
        )
        return response

    leads = db.execute(select(Lead).where(Lead.id.in_(ids))).scalars().all()
    leads_map = {l.id: l for l in leads}

    sent_count = 0
    skipped_count = 0

    for lead_id in ids:
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

    meta = {
        "template_id": template.id,
        "lead_ids": ids,
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "source": "leads_hot",
    }
    log_action(
        db=db,
        actor=user,
        action="LEAD_HOT_BULK_EMAIL",
        target_type="lead",
        meta=meta,
    )

    message = f"{sent_count}件のメールを送信しました"
    if skipped_count:
        message += f"（{skipped_count}件は送信対象外またはエラー）"

    response = RedirectResponse(url=f"/ui/leads/hot?message={message}", status_code=302)
    return response
