"""UI endpoints for hot leads (engagement scoring)"""
import math
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, and_

from src.ma_tool.database import get_db
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.engagement_event import EngagementEvent
from src.ma_tool.models.user import User
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings

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
    })
