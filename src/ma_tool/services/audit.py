"""Audit logging service"""
import json
from typing import Optional, Any
from sqlalchemy.orm import Session

from src.ma_tool.models.audit_log import AuditLog
from src.ma_tool.models.user import User


def log_action(
    db: Session,
    actor: User,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    meta: Optional[dict] = None
) -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=actor.id,
        actor_role_snapshot=actor.role.value,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta_json=json.dumps(meta) if meta else None
    )
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log
