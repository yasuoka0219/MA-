"""Template management API endpoints"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from src.ma_tool.api.deps import (
    DbSession, CurrentUser, EditorUser, ApproverUser,
    can_edit_template, can_approve_template
)
from src.ma_tool.models.template import TemplateStatus
from src.ma_tool.schemas.template import (
    TemplateCreate, TemplateUpdate, TemplateReject, TemplateClone,
    TemplateResponse, TemplateListResponse, VariableInfo
)
from src.ma_tool.services.template import (
    get_template_by_id, get_templates, create_template, update_template,
    submit_for_approval, approve_template, reject_template, clone_template,
    delete_template, AVAILABLE_VARIABLES,
    TemplateNotFoundError, TemplatePermissionError, TemplateStateError, TemplateError
)

router = APIRouter(prefix="/api/templates", tags=["templates"])


def template_to_response(template, db) -> TemplateResponse:
    creator_name = template.creator.name if template.creator else None
    approver_name = template.approver.name if template.approver else None
    
    return TemplateResponse(
        id=template.id,
        name=template.name,
        subject=template.subject,
        body_html=template.body_html,
        status=template.status,
        created_by=template.created_by,
        created_by_name=creator_name,
        approved_by=template.approved_by,
        approved_by_name=approver_name,
        approved_at=template.approved_at,
        rejected_reason=template.rejected_reason,
        created_at=template.created_at,
        updated_at=template.updated_at
    )


@router.get("", response_model=TemplateListResponse)
def list_templates(
    db: DbSession,
    user: CurrentUser,
    status: Optional[TemplateStatus] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    templates = get_templates(db, status=status, limit=limit, offset=offset)
    return TemplateListResponse(
        templates=[template_to_response(t, db) for t in templates],
        total=len(templates)
    )


@router.post("", response_model=TemplateResponse, status_code=201)
def create_new_template(
    db: DbSession,
    user: EditorUser,
    data: TemplateCreate
):
    try:
        template = create_template(db, user, data.name, data.subject, data.body_html)
        db.commit()
        db.refresh(template)
        return template_to_response(template, db)
    except TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/variables", response_model=list[VariableInfo])
def get_available_variables(user: CurrentUser):
    return [VariableInfo(**v) for v in AVAILABLE_VARIABLES]


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    db: DbSession,
    user: CurrentUser,
    template_id: int
):
    template = get_template_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template_to_response(template, db)


@router.put("/{template_id}", response_model=TemplateResponse)
def update_existing_template(
    db: DbSession,
    user: EditorUser,
    template_id: int,
    data: TemplateUpdate
):
    try:
        template = update_template(
            db, user, template_id,
            name=data.name, subject=data.subject, body_html=data.body_html
        )
        db.commit()
        db.refresh(template)
        return template_to_response(template, db)
    except TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except TemplateStateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{template_id}/submit", response_model=TemplateResponse)
def submit_template(
    db: DbSession,
    user: EditorUser,
    template_id: int
):
    try:
        template = submit_for_approval(db, user, template_id)
        db.commit()
        db.refresh(template)
        return template_to_response(template, db)
    except TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except TemplateStateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{template_id}/approve", response_model=TemplateResponse)
def approve_template_endpoint(
    db: DbSession,
    user: ApproverUser,
    template_id: int
):
    try:
        template = approve_template(db, user, template_id)
        db.commit()
        db.refresh(template)
        return template_to_response(template, db)
    except TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except TemplateStateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{template_id}/reject", response_model=TemplateResponse)
def reject_template_endpoint(
    db: DbSession,
    user: ApproverUser,
    template_id: int,
    data: TemplateReject
):
    try:
        template = reject_template(db, user, template_id, data.reason)
        db.commit()
        db.refresh(template)
        return template_to_response(template, db)
    except TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except TemplateStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{template_id}/clone", response_model=TemplateResponse, status_code=201)
def clone_template_endpoint(
    db: DbSession,
    user: EditorUser,
    template_id: int,
    data: Optional[TemplateClone] = None
):
    try:
        new_name = data.new_name if data else None
        template = clone_template(db, user, template_id, new_name)
        db.commit()
        db.refresh(template)
        return template_to_response(template, db)
    except TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{template_id}", status_code=204)
def delete_template_endpoint(
    db: DbSession,
    user: CurrentUser,
    template_id: int
):
    try:
        delete_template(db, user, template_id)
        db.commit()
    except TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except TemplateStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
