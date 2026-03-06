"""Audit logging service"""
import json
from typing import Optional
from sqlalchemy.orm import Session

from src.ma_tool.models.audit_log import AuditLog
from src.ma_tool.models.user import User


def log_action(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    meta: Optional[dict] = None,
    details: Optional[dict] = None,
    actor: Optional[User] = None,
    actor_id: Optional[int] = None,
    actor_role_snapshot: Optional[str] = None,
) -> AuditLog:
    """監査ログを記録する。actor を渡すか、actor_id/actor_role_snapshot を渡す（システム実行時は両方 None で actor_role_snapshot は 'system'）。meta と details は同じ扱い。"""
    if actor is not None:
        user_id, role_snapshot = actor.id, actor.role.value
    else:
        user_id = actor_id
        role_snapshot = actor_role_snapshot if actor_role_snapshot is not None else "system"
    payload = meta if meta is not None else details
    audit_log = AuditLog(
        actor_user_id=user_id,
        actor_role_snapshot=role_snapshot,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta_json=json.dumps(payload) if payload else None
    )
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log
