"""UI endpoints for LINE identity management"""
import json
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import get_db
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.line_identity import LineIdentity, LineIdentityStatus
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.models.audit_log import AuditLog
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings

router = APIRouter(prefix="/ui", tags=["UI LINE"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


def create_audit_log(db: Session, user: User, action: str, target_type: str, target_id: int, meta: Optional[dict] = None):
    log = AuditLog(
        actor_user_id=user.id,
        actor_role_snapshot=user.role.value,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta_json=json.dumps(meta) if meta else None,
    )
    db.add(log)
    db.commit()


@router.get("/line-identities", response_class=HTMLResponse)
async def line_identities_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    status_filter: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    query = select(LineIdentity)
    
    if status_filter:
        try:
            status = LineIdentityStatus(status_filter)
            query = query.where(LineIdentity.status == status)
        except ValueError:
            pass
    
    query = query.order_by(LineIdentity.created_at.desc())
    
    per_page = 50
    offset = (page - 1) * per_page
    identities = db.execute(query.offset(offset).limit(per_page)).scalars().all()
    
    lead_ids = [i.lead_id for i in identities if i.lead_id]
    leads = {}
    if lead_ids:
        lead_records = db.execute(select(Lead).where(Lead.id.in_(lead_ids))).scalars().all()
        leads = {l.id: l for l in lead_records}
    
    blocked_lead_ids = [l.id for l in db.execute(select(Lead).where(Lead.line_blocked == True)).scalars().all()]
    blocked_count = db.execute(select(LineIdentity).where(LineIdentity.lead_id.in_(blocked_lead_ids))).scalars().all().__len__() if blocked_lead_ids else 0
    
    status_counts = {
        "all": db.execute(select(LineIdentity)).scalars().all().__len__(),
        "unlinked": db.execute(select(LineIdentity).where(LineIdentity.status == LineIdentityStatus.UNLINKED)).scalars().all().__len__(),
        "linked": db.execute(select(LineIdentity).where(LineIdentity.status == LineIdentityStatus.LINKED)).scalars().all().__len__(),
        "blocked": blocked_count,
    }
    
    return templates.TemplateResponse("ui_line_identities.html", {
        **get_base_context(request, user),
        "identities": identities,
        "leads": leads,
        "status_filter": status_filter or "",
        "status_counts": status_counts,
        "page": page,
        "can_unlink": user.role == UserRole.ADMIN,
    })


@router.get("/line-identities/{identity_id}/link-form", response_class=HTMLResponse)
async def link_form(
    request: Request,
    identity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    identity = db.execute(
        select(LineIdentity).where(LineIdentity.id == identity_id)
    ).scalar_one_or_none()
    
    if not identity:
        return HTMLResponse("<div class='alert alert-danger'>不明なIDです</div>", status_code=404)
    
    return templates.TemplateResponse("ui_line_link_form.html", {
        **get_base_context(request, user),
        "identity": identity,
    })


@router.post("/line-identities/{identity_id}/search-lead", response_class=HTMLResponse)
async def search_lead_for_link(
    request: Request,
    identity_id: int,
    email: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    identity = db.execute(
        select(LineIdentity).where(LineIdentity.id == identity_id)
    ).scalar_one_or_none()
    
    if not identity:
        return HTMLResponse("<div class='alert alert-danger'>不明なIDです</div>", status_code=404)
    
    leads = db.execute(
        select(Lead).where(Lead.email.ilike(f"%{email}%"))
    ).scalars().all()
    
    return templates.TemplateResponse("ui_line_search_results.html", {
        **get_base_context(request, user),
        "identity": identity,
        "leads": leads,
        "search_email": email,
    })


@router.post("/line-identities/{identity_id}/link", response_class=HTMLResponse)
async def link_identity(
    request: Request,
    identity_id: int,
    lead_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    identity = db.execute(
        select(LineIdentity).where(LineIdentity.id == identity_id)
    ).scalar_one_or_none()
    
    if not identity:
        return HTMLResponse("<div class='alert alert-danger'>不明なIDです</div>", status_code=404)
    
    lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    if not lead:
        return HTMLResponse("<div class='alert alert-danger'>リードが見つかりません</div>", status_code=404)
    
    identity.lead_id = lead_id
    identity.status = LineIdentityStatus.LINKED
    db.commit()
    
    create_audit_log(db, user, "link", "line_identity", identity_id, {"lead_id": lead_id, "lead_email": lead.email})
    
    response = Response(
        content=f"""<span class="badge bg-success">紐付け済</span>
        <small class="text-muted ms-2">{lead.email}</small>""",
        media_type="text/html"
    )
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "紐付けしました", "type": "success"}})
    return response


@router.post("/line-identities/{identity_id}/unlink", response_class=HTMLResponse)
async def unlink_identity(
    request: Request,
    identity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if user.role != UserRole.ADMIN:
        return HTMLResponse("<div class='alert alert-danger'>管理者権限が必要です</div>", status_code=403)
    
    identity = db.execute(
        select(LineIdentity).where(LineIdentity.id == identity_id)
    ).scalar_one_or_none()
    
    if not identity:
        return HTMLResponse("<div class='alert alert-danger'>不明なIDです</div>", status_code=404)
    
    old_lead_id = identity.lead_id
    identity.lead_id = None
    identity.status = LineIdentityStatus.UNLINKED
    db.commit()
    
    create_audit_log(db, user, "unlink", "line_identity", identity_id, {"old_lead_id": old_lead_id})
    
    response = Response(
        content="""<span class="badge bg-secondary">未紐付け</span>""",
        media_type="text/html"
    )
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "紐付け解除しました", "type": "success"}})
    return response
