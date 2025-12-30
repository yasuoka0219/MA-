"""UI Dashboard endpoint with KPI cards"""
from typing import Optional
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from src.ma_tool.database import get_db
from src.ma_tool.models.user import User
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.template import Template, TemplateStatus
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.models.send_log import SendLog, SendStatus
from src.ma_tool.config import settings
from src.ma_tool.api.endpoints.ui_auth import get_base_context

router = APIRouter(prefix="/ui", tags=["UI Dashboard"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/ui/login", status_code=302)
    
    leads_count = db.execute(select(func.count()).select_from(Lead)).scalar() or 0
    templates_approved = db.execute(
        select(func.count()).select_from(Template).where(Template.status == TemplateStatus.APPROVED)
    ).scalar() or 0
    templates_total = db.execute(select(func.count()).select_from(Template)).scalar() or 0
    scenarios_enabled = db.execute(
        select(func.count()).select_from(Scenario).where(Scenario.is_enabled == True)
    ).scalar() or 0
    scenarios_total = db.execute(select(func.count()).select_from(Scenario)).scalar() or 0
    
    sent_count = db.execute(
        select(func.count()).select_from(SendLog).where(SendLog.status == SendStatus.SENT)
    ).scalar() or 0
    failed_count = db.execute(
        select(func.count()).select_from(SendLog).where(SendLog.status == SendStatus.FAILED)
    ).scalar() or 0
    
    recent_logs = db.execute(
        select(SendLog)
        .order_by(SendLog.created_at.desc())
        .limit(10)
    ).scalars().all()
    
    return templates.TemplateResponse("ui_dashboard.html", {
        **get_base_context(request, user),
        "leads_count": leads_count,
        "templates_approved": templates_approved,
        "templates_total": templates_total,
        "scenarios_enabled": scenarios_enabled,
        "scenarios_total": scenarios_total,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "recent_logs": recent_logs,
    })


@router.get("", response_class=HTMLResponse)
async def ui_root(request: Request):
    """Redirect /ui to dashboard or login"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    return RedirectResponse(url="/ui/login", status_code=302)
