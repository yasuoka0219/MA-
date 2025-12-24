"""UI endpoints for lead management"""
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from src.ma_tool.database import get_db
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.line_identity import LineIdentity, LineIdentityStatus
from src.ma_tool.models.user import User
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings

router = APIRouter(prefix="/ui", tags=["UI Leads"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


@router.get("/leads", response_class=HTMLResponse)
async def leads_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    search: Optional[str] = Query(None),
    graduation_year: Optional[int] = Query(None),
    interest: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    query = select(Lead)
    
    if search:
        query = query.where(
            or_(
                Lead.email.ilike(f"%{search}%"),
                Lead.school_name.ilike(f"%{search}%"),
                Lead.name.ilike(f"%{search}%"),
            )
        )
    if graduation_year:
        query = query.where(Lead.graduation_year == graduation_year)
    if interest:
        query = query.where(Lead.interest_tags.ilike(f"%{interest}%"))
    
    query = query.order_by(Lead.created_at.desc())
    
    per_page = 50
    offset = (page - 1) * per_page
    leads = db.execute(query.offset(offset).limit(per_page)).scalars().all()
    
    total = db.execute(select(Lead.id)).scalars().all()
    total_count = len(total)
    
    line_identities = {}
    lead_ids = [l.id for l in leads]
    if lead_ids:
        identities = db.execute(
            select(LineIdentity).where(LineIdentity.lead_id.in_(lead_ids))
        ).scalars().all()
        for identity in identities:
            line_identities[identity.lead_id] = identity
    
    graduation_years = db.execute(
        select(Lead.graduation_year).distinct().where(Lead.graduation_year.isnot(None)).order_by(Lead.graduation_year.desc())
    ).scalars().all()
    
    return templates.TemplateResponse("ui_leads_list.html", {
        **get_base_context(request, user),
        "leads": leads,
        "line_identities": line_identities,
        "search": search or "",
        "graduation_year": graduation_year,
        "interest": interest or "",
        "page": page,
        "total_count": total_count,
        "per_page": per_page,
        "graduation_years": graduation_years,
    })


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_detail(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    if not lead:
        return HTMLResponse("<h1>リードが見つかりません</h1>", status_code=404)
    
    line_identity = db.execute(
        select(LineIdentity).where(LineIdentity.lead_id == lead_id)
    ).scalar_one_or_none()
    
    return templates.TemplateResponse("ui_lead_detail.html", {
        **get_base_context(request, user),
        "lead": lead,
        "line_identity": line_identity,
    })
