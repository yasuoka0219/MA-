"""UI endpoints for send log viewing"""
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from zoneinfo import ZoneInfo

from src.ma_tool.database import get_db
from src.ma_tool.models.send_log import SendLog, SendStatus, SendChannel
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.models.template import Template
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings
from src.ma_tool.services.email import EmailService, get_email_service
from src.ma_tool.services.scheduler import send_single_email
from src.ma_tool.services.audit import log_action

JST = ZoneInfo("Asia/Tokyo")

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
    lead_id: Optional[int] = Query(None),
    days: int = Query(7, ge=1, le=90),
    page: int = Query(1, ge=1),
):
    query = select(SendLog)
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = query.where(SendLog.created_at >= cutoff)
    
    if lead_id:
        query = query.where(SendLog.lead_id == lead_id)
    
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
    
    # 総件数を取得（order_byの前に）
    count_query = select(func.count(SendLog.id))
    cutoff = datetime.utcnow() - timedelta(days=days)
    count_query = count_query.where(SendLog.created_at >= cutoff)
    
    if lead_id:
        count_query = count_query.where(SendLog.lead_id == lead_id)
    
    if status_filter:
        try:
            status = SendStatus(status_filter)
            count_query = count_query.where(SendLog.status == status)
        except ValueError:
            pass
    
    if channel_filter:
        try:
            channel = SendChannel(channel_filter)
            count_query = count_query.where(SendLog.channel == channel)
        except ValueError:
            pass
    
    total_count = db.execute(count_query).scalar() or 0
    
    query = query.order_by(SendLog.created_at.desc())
    
    per_page = 50
    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    offset = (page - 1) * per_page
    logs = db.execute(query.offset(offset).limit(per_page)).scalars().all()
    
    start_item = offset + 1 if total_count > 0 else 0
    end_item = min(offset + per_page, total_count)
    
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
    
    # リード情報を取得（lead_idフィルタがある場合）
    lead = None
    if lead_id:
        lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    
    return templates.TemplateResponse("ui_send_logs.html", {
        **get_base_context(request, user),
        "logs": logs,
        "leads": leads_map,
        "scenarios": scenarios_map,
        "status_filter": status_filter or "",
        "channel_filter": channel_filter or "",
        "lead_id": lead_id,
        "lead": lead,
        "days": days,
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "start_item": start_item,
        "end_item": end_item,
        "status_counts": status_counts,
    })


def can_edit(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.EDITOR]


@router.get("/send-logs/{log_id}", response_class=HTMLResponse)
async def send_log_detail(
    request: Request,
    log_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    message: Optional[str] = Query(None),
):
    """送信ログの詳細を表示"""
    log = db.execute(select(SendLog).where(SendLog.id == log_id)).scalar_one_or_none()
    if not log:
        return HTMLResponse("<h1>送信ログが見つかりません</h1>", status_code=404)
    
    lead = db.get(Lead, log.lead_id)
    scenario = db.get(Scenario, log.scenario_id)
    template = None
    if scenario:
        template = db.get(Template, scenario.template_id)
    
    return templates.TemplateResponse("ui_send_log_detail.html", {
        **get_base_context(request, user),
        "log": log,
        "lead": lead,
        "scenario": scenario,
        "template": template,
        "can_edit": can_edit(user),
        "message": message,
    })


@router.post("/send-logs/{log_id}/resend")
async def send_log_resend(
    request: Request,
    log_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """送信ログの再送信（admin/editorのみ）"""
    if not can_edit(user):
        return HTMLResponse("<div class='alert alert-danger'>権限がありません</div>", status_code=403)
    
    log = db.execute(select(SendLog).where(SendLog.id == log_id)).scalar_one_or_none()
    if not log:
        return HTMLResponse("<div class='alert alert-danger'>送信ログが見つかりません</div>", status_code=404)
    
    # 失敗またはブロックされたログのみ再送信可能
    previous_status = log.status.value
    if log.status not in [SendStatus.FAILED, SendStatus.BLOCKED]:
        return HTMLResponse(
            f"<div class='alert alert-warning'>このログは再送信できません（ステータス: {log.status.value}）</div>",
            status_code=400
        )
    
    # ステータスをSCHEDULEDに戻して再送信
    log.status = SendStatus.SCHEDULED
    log.scheduled_for = datetime.now(JST)
    log.attempt_count = 0
    log.error_message = None
    db.commit()
    
    # 監査ログに記録
    log_action(
        db=db,
        actor=user,
        action="SEND_LOG_RESEND",
        target_type="send_log",
        target_id=log.id,
        meta={
            "lead_id": log.lead_id,
            "scenario_id": log.scenario_id,
            "previous_status": previous_status
        }
    )
    
    # 即座に送信を試みる
    email_service = get_email_service()
    success = send_single_email(db, log, email_service)
    db.commit()
    
    if success:
        msg = "再送信が成功しました"
        msg_type = "success"
    else:
        msg = f"再送信を試みましたが失敗しました: {log.error_message or '不明なエラー'}"
        msg_type = "warning"
    
    response = RedirectResponse(url=f"/ui/send-logs/{log_id}?message={msg}", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": msg_type}})
    return response
