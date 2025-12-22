"""Template management service with approval workflow"""
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from src.ma_tool.models.template import Template, TemplateStatus
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.services.audit import log_action


class TemplateError(Exception):
    """Base exception for template operations"""
    pass


class TemplateNotFoundError(TemplateError):
    pass


class TemplatePermissionError(TemplateError):
    pass


class TemplateStateError(TemplateError):
    pass


def get_template_by_id(db: Session, template_id: int) -> Optional[Template]:
    return db.execute(
        select(Template).where(Template.id == template_id)
    ).scalar_one_or_none()


def get_templates(
    db: Session,
    status: Optional[TemplateStatus] = None,
    created_by: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Template]:
    query = select(Template).order_by(Template.updated_at.desc())
    
    if status:
        query = query.where(Template.status == status)
    if created_by:
        query = query.where(Template.created_by == created_by)
    
    query = query.limit(limit).offset(offset)
    return list(db.execute(query).scalars().all())


def create_template(
    db: Session,
    user: User,
    name: str,
    subject: str,
    body_html: str
) -> Template:
    if user.role not in [UserRole.ADMIN, UserRole.EDITOR]:
        raise TemplatePermissionError("Only editors and admins can create templates")
    
    template = Template(
        name=name,
        subject=subject,
        body_html=body_html,
        status=TemplateStatus.DRAFT,
        created_by=user.id
    )
    db.add(template)
    db.flush()
    
    log_action(
        db=db,
        action="template_created",
        actor_id=user.id,
        actor_role_snapshot=user.role.value,
        target_type="template",
        target_id=template.id,
        details={"name": name, "subject": subject}
    )
    
    return template


def update_template(
    db: Session,
    user: User,
    template_id: int,
    name: Optional[str] = None,
    subject: Optional[str] = None,
    body_html: Optional[str] = None
) -> Template:
    template = get_template_by_id(db, template_id)
    if not template:
        raise TemplateNotFoundError(f"Template {template_id} not found")
    
    if user.role not in [UserRole.ADMIN, UserRole.EDITOR]:
        raise TemplatePermissionError("Only editors and admins can edit templates")
    
    if template.status == TemplateStatus.APPROVED:
        raise TemplateStateError("Approved templates cannot be edited. Please clone to create a new version.")
    
    changes = {}
    if name is not None and name != template.name:
        changes["name"] = {"old": template.name, "new": name}
        template.name = name
    if subject is not None and subject != template.subject:
        changes["subject"] = {"old": template.subject, "new": subject}
        template.subject = subject
    if body_html is not None and body_html != template.body_html:
        changes["body_html"] = "updated"
        template.body_html = body_html
    
    if template.status == TemplateStatus.REJECTED:
        template.status = TemplateStatus.DRAFT
        template.rejected_reason = None
        changes["status"] = {"old": "rejected", "new": "draft"}
    
    if changes:
        log_action(
            db=db,
            action="template_updated",
            actor_id=user.id,
            actor_role_snapshot=user.role.value,
            target_type="template",
            target_id=template.id,
            details=changes
        )
    
    return template


def submit_for_approval(
    db: Session,
    user: User,
    template_id: int
) -> Template:
    template = get_template_by_id(db, template_id)
    if not template:
        raise TemplateNotFoundError(f"Template {template_id} not found")
    
    if user.role not in [UserRole.ADMIN, UserRole.EDITOR]:
        raise TemplatePermissionError("Only editors and admins can submit templates for approval")
    
    if template.status not in [TemplateStatus.DRAFT, TemplateStatus.REJECTED]:
        raise TemplateStateError(f"Cannot submit template with status '{template.status.value}' for approval")
    
    template.status = TemplateStatus.PENDING
    template.rejected_reason = None
    
    log_action(
        db=db,
        action="template_submitted",
        actor_id=user.id,
        actor_role_snapshot=user.role.value,
        target_type="template",
        target_id=template.id,
        details={"new_status": "pending"}
    )
    
    return template


def approve_template(
    db: Session,
    user: User,
    template_id: int
) -> Template:
    template = get_template_by_id(db, template_id)
    if not template:
        raise TemplateNotFoundError(f"Template {template_id} not found")
    
    if user.role not in [UserRole.ADMIN, UserRole.APPROVER]:
        raise TemplatePermissionError("Only approvers and admins can approve templates")
    
    if template.status != TemplateStatus.PENDING:
        raise TemplateStateError(f"Cannot approve template with status '{template.status.value}'")
    
    template.status = TemplateStatus.APPROVED
    template.approved_by = user.id
    template.approved_at = datetime.now(timezone.utc)
    template.rejected_reason = None
    
    log_action(
        db=db,
        action="template_approved",
        actor_id=user.id,
        actor_role_snapshot=user.role.value,
        target_type="template",
        target_id=template.id,
        details={"approved_at": template.approved_at.isoformat()}
    )
    
    return template


def reject_template(
    db: Session,
    user: User,
    template_id: int,
    reason: str
) -> Template:
    template = get_template_by_id(db, template_id)
    if not template:
        raise TemplateNotFoundError(f"Template {template_id} not found")
    
    if user.role not in [UserRole.ADMIN, UserRole.APPROVER]:
        raise TemplatePermissionError("Only approvers and admins can reject templates")
    
    if template.status != TemplateStatus.PENDING:
        raise TemplateStateError(f"Cannot reject template with status '{template.status.value}'")
    
    if not reason or not reason.strip():
        raise TemplateError("Rejection reason is required")
    
    template.status = TemplateStatus.REJECTED
    template.rejected_reason = reason.strip()
    template.approved_by = None
    template.approved_at = None
    
    log_action(
        db=db,
        action="template_rejected",
        actor_id=user.id,
        actor_role_snapshot=user.role.value,
        target_type="template",
        target_id=template.id,
        details={"reason": reason.strip()}
    )
    
    return template


def clone_template(
    db: Session,
    user: User,
    template_id: int,
    new_name: Optional[str] = None
) -> Template:
    template = get_template_by_id(db, template_id)
    if not template:
        raise TemplateNotFoundError(f"Template {template_id} not found")
    
    if user.role not in [UserRole.ADMIN, UserRole.EDITOR]:
        raise TemplatePermissionError("Only editors and admins can clone templates")
    
    cloned = Template(
        name=new_name or f"{template.name} (copy)",
        subject=template.subject,
        body_html=template.body_html,
        status=TemplateStatus.DRAFT,
        created_by=user.id
    )
    db.add(cloned)
    db.flush()
    
    log_action(
        db=db,
        action="template_cloned",
        actor_id=user.id,
        actor_role_snapshot=user.role.value,
        target_type="template",
        target_id=cloned.id,
        details={"cloned_from": template.id, "original_name": template.name}
    )
    
    return cloned


def delete_template(
    db: Session,
    user: User,
    template_id: int
) -> bool:
    template = get_template_by_id(db, template_id)
    if not template:
        raise TemplateNotFoundError(f"Template {template_id} not found")
    
    if user.role != UserRole.ADMIN:
        raise TemplatePermissionError("Only admins can delete templates")
    
    if template.status == TemplateStatus.APPROVED:
        raise TemplateStateError("Approved templates cannot be deleted")
    
    log_action(
        db=db,
        action="template_deleted",
        actor_id=user.id,
        actor_role_snapshot=user.role.value,
        target_type="template",
        target_id=template.id,
        details={"name": template.name}
    )
    
    db.delete(template)
    return True


AVAILABLE_VARIABLES = [
    {"name": "{{name}}", "description": "リード氏名"},
    {"name": "{{email}}", "description": "メールアドレス"},
    {"name": "{{school_name}}", "description": "高校名"},
    {"name": "{{graduation_year}}", "description": "卒業年度"},
    {"name": "{{interest_tags}}", "description": "興味・志望分野"},
    {"name": "{{event_name}}", "description": "イベント名"},
    {"name": "{{event_date}}", "description": "イベント開催日"},
    {"name": "{{unsubscribe_url}}", "description": "配信停止URL"},
]
