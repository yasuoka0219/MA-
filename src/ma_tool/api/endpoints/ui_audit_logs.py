"""UI endpoints for audit log viewing"""
import json
import math
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func

from src.ma_tool.database import get_db
from src.ma_tool.models.audit_log import AuditLog
from src.ma_tool.models.user import User
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings

router = APIRouter(prefix="/ui", tags=["UI Audit Logs"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    action_filter: Optional[str] = Query(None),
    user_filter: Optional[int] = Query(None),
    target_type_filter: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
    page: int = Query(1, ge=1),
):
    """監査ログ一覧を表示"""
    query = select(AuditLog)
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = query.where(AuditLog.created_at >= cutoff)
    
    if action_filter:
        query = query.where(AuditLog.action.ilike(f"%{action_filter}%"))
    
    if user_filter:
        query = query.where(AuditLog.actor_user_id == user_filter)
    
    if target_type_filter:
        query = query.where(AuditLog.target_type == target_type_filter)
    
    # 総件数を取得
    count_query = select(func.count(AuditLog.id))
    count_query = count_query.where(AuditLog.created_at >= cutoff)
    
    if action_filter:
        count_query = count_query.where(AuditLog.action.ilike(f"%{action_filter}%"))
    
    if user_filter:
        count_query = count_query.where(AuditLog.actor_user_id == user_filter)
    
    if target_type_filter:
        count_query = count_query.where(AuditLog.target_type == target_type_filter)
    
    total_count = db.execute(count_query).scalar() or 0
    
    query = query.order_by(AuditLog.created_at.desc())
    
    per_page = 50
    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    offset = (page - 1) * per_page
    logs = db.execute(query.offset(offset).limit(per_page)).scalars().all()
    
    start_item = offset + 1 if total_count > 0 else 0
    end_item = min(offset + per_page, total_count)
    
    # ユーザー情報を取得
    user_ids = list(set([log.actor_user_id for log in logs]))
    users_map = {}
    if user_ids:
        user_records = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
        users_map = {u.id: u for u in user_records}
    
    # アクション一覧を取得（フィルタ用）
    action_list = db.execute(
        select(AuditLog.action).distinct().where(AuditLog.created_at >= cutoff)
    ).scalars().all()
    
    # ターゲットタイプ一覧を取得（フィルタ用）
    target_types = db.execute(
        select(AuditLog.target_type).distinct().where(AuditLog.created_at >= cutoff)
    ).scalars().all()
    
    # 全ユーザー一覧を取得（フィルタ用）
    all_users = db.execute(select(User).order_by(User.name)).scalars().all()
    
    return templates.TemplateResponse("ui_audit_logs.html", {
        **get_base_context(request, user),
        "logs": logs,
        "users": users_map,
        "all_users": all_users,
        "action_filter": action_filter or "",
        "user_filter": user_filter,
        "target_type_filter": target_type_filter or "",
        "days": days,
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "start_item": start_item,
        "end_item": end_item,
        "action_list": sorted(set(action_list)),
        "target_types": sorted(set(target_types)),
    })
