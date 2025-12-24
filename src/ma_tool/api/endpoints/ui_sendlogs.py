"""UI endpoints for send log viewing"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from src.ma_tool.database import get_db
from src.ma_tool.models.send_log import SendLog, SendStatus, SendChannel
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.models.user import User
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings

router = APIRouter(prefix="/ui", tags=["UI Send Logs"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


@router.get("/send-logs", response_class=HTMLResponse)
async def send_logs_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    status_filter: Optional[str] = Query(None),
    channel_filter: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
    page: int = Query(1, ge=1),
):
    query = select(SendLog)
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = query.where(SendLog.created_at >= cutoff)
    
    if status_filter:
        try:
            status = SendStatus(status_filter)
            query = query.where(SendLog.status == status)
        except ValueError:
            pass
    
    if channel_filter:
        try:
            channel = SendChannel(channel_filter)
            query = query.where(SendLog.channel == channel)
        except ValueError:
            pass
    
    query = query.order_by(SendLog.created_at.desc())
    
    per_page = 50
    offset = (page - 1) * per_page
    logs = db.execute(query.offset(offset).limit(per_page)).scalars().all()
    
    lead_ids = list(set([l.lead_id for l in logs]))
    scenario_ids = list(set([l.scenario_id for l in logs]))
    
    leads_map = {}
    scenarios_map = {}
    
    if lead_ids:
        lead_records = db.execute(select(Lead).where(Lead.id.in_(lead_ids))).scalars().all()
        leads_map = {l.id: l for l in lead_records}
    
    if scenario_ids:
        scenario_records = db.execute(select(Scenario).where(Scenario.id.in_(scenario_ids))).scalars().all()
        scenarios_map = {s.id: s for s in scenario_records}
    
    status_counts = {
        "all": db.execute(select(SendLog).where(SendLog.created_at >= cutoff)).scalars().all().__len__(),
        "scheduled": db.execute(select(SendLog).where(and_(SendLog.created_at >= cutoff, SendLog.status == SendStatus.SCHEDULED))).scalars().all().__len__(),
        "sent": db.execute(select(SendLog).where(and_(SendLog.created_at >= cutoff, SendLog.status == SendStatus.SENT))).scalars().all().__len__(),
        "failed": db.execute(select(SendLog).where(and_(SendLog.created_at >= cutoff, SendLog.status == SendStatus.FAILED))).scalars().all().__len__(),
        "blocked": db.execute(select(SendLog).where(and_(SendLog.created_at >= cutoff, SendLog.status == SendStatus.BLOCKED))).scalars().all().__len__(),
    }
    
    return templates.TemplateResponse("ui_send_logs.html", {
        **get_base_context(request, user),
        "logs": logs,
        "leads": leads_map,
        "scenarios": scenarios_map,
        "status_filter": status_filter or "",
        "channel_filter": channel_filter or "",
        "days": days,
        "page": page,
        "per_page": per_page,
        "status_counts": status_counts,
    })
