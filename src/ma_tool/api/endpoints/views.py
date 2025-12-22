"""Web views for template management UI"""
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from src.ma_tool.database import SessionLocal
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.models.template import Template, TemplateStatus
from src.ma_tool.services.template import (
    get_templates, get_template_by_id, create_template, update_template,
    submit_for_approval, approve_template, reject_template, clone_template,
    AVAILABLE_VARIABLES,
    TemplateNotFoundError, TemplatePermissionError, TemplateStateError
)
from src.ma_tool.api.deps import can_edit_template, can_approve_template

router = APIRouter(tags=["views"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_user_from_cookie(request: Request) -> User:
    db = SessionLocal()
    try:
        user_id = request.cookies.get("user_id", "1")
        try:
            user_id = int(user_id)
        except ValueError:
            user_id = 1
        
        user = db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        ).scalar_one_or_none()
        
        if not user:
            user = db.execute(
                select(User).where(User.is_active == True)
            ).scalars().first()
        
        return user
    finally:
        db.close()


def get_all_users() -> list[User]:
    db = SessionLocal()
    try:
        return list(db.execute(
            select(User).where(User.is_active == True).order_by(User.id)
        ).scalars().all())
    finally:
        db.close()


def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/templates", response_class=HTMLResponse)
async def template_list(
    request: Request,
    status: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
    message_type: Optional[str] = Query(None)
):
    user = get_user_from_cookie(request)
    users = get_all_users()
    
    db = SessionLocal()
    try:
        status_filter = None
        if status:
            try:
                status_filter = TemplateStatus(status)
            except ValueError:
                pass
        
        template_list = get_templates(db, status=status_filter)
        
        return templates.TemplateResponse("template_list.html", {
            "request": request,
            "templates": template_list,
            "status_filter": status,
            "current_user": user,
            "users": users,
            "can_edit": can_edit_template(user),
            "can_approve": can_approve_template(user),
            "message": message,
            "message_type": message_type
        })
    finally:
        db.close()


@router.get("/templates/new", response_class=HTMLResponse)
async def new_template_form(request: Request):
    user = get_user_from_cookie(request)
    users = get_all_users()
    
    if not can_edit_template(user):
        return RedirectResponse(
            url="/templates?message=You don't have permission to create templates&message_type=error",
            status_code=303
        )
    
    return templates.TemplateResponse("template_form.html", {
        "request": request,
        "template": None,
        "variables": AVAILABLE_VARIABLES,
        "current_user": user,
        "users": users,
        "can_edit": can_edit_template(user),
        "can_approve": can_approve_template(user)
    })


@router.post("/templates", response_class=HTMLResponse)
async def create_template_form(
    request: Request,
    name: str = Form(...),
    subject: str = Form(...),
    body_html: str = Form(...)
):
    user = get_user_from_cookie(request)
    
    if not can_edit_template(user):
        return RedirectResponse(
            url="/templates?message=You don't have permission to create templates&message_type=error",
            status_code=303
        )
    
    db = SessionLocal()
    try:
        template = create_template(db, user, name, subject, body_html)
        db.commit()
        return RedirectResponse(
            url=f"/templates/{template.id}?message=Template created successfully&message_type=success",
            status_code=303
        )
    except Exception as e:
        db.rollback()
        users = get_all_users()
        return templates.TemplateResponse("template_form.html", {
            "request": request,
            "template": None,
            "variables": AVAILABLE_VARIABLES,
            "current_user": user,
            "users": users,
            "can_edit": can_edit_template(user),
            "can_approve": can_approve_template(user),
            "message": str(e),
            "message_type": "error"
        })
    finally:
        db.close()


@router.get("/templates/{template_id}", response_class=HTMLResponse)
async def template_detail(
    request: Request,
    template_id: int,
    message: Optional[str] = Query(None),
    message_type: Optional[str] = Query(None)
):
    user = get_user_from_cookie(request)
    users = get_all_users()
    
    db = SessionLocal()
    try:
        template = get_template_by_id(db, template_id)
        if not template:
            return RedirectResponse(
                url="/templates?message=Template not found&message_type=error",
                status_code=303
            )
        
        return templates.TemplateResponse("template_detail.html", {
            "request": request,
            "template": template,
            "current_user": user,
            "users": users,
            "can_edit": can_edit_template(user),
            "can_approve": can_approve_template(user),
            "message": message,
            "message_type": message_type
        })
    finally:
        db.close()


@router.get("/templates/{template_id}/edit", response_class=HTMLResponse)
async def edit_template_form(request: Request, template_id: int):
    user = get_user_from_cookie(request)
    users = get_all_users()
    
    if not can_edit_template(user):
        return RedirectResponse(
            url=f"/templates/{template_id}?message=You don't have permission to edit templates&message_type=error",
            status_code=303
        )
    
    db = SessionLocal()
    try:
        template = get_template_by_id(db, template_id)
        if not template:
            return RedirectResponse(
                url="/templates?message=Template not found&message_type=error",
                status_code=303
            )
        
        if template.status == TemplateStatus.APPROVED:
            return RedirectResponse(
                url=f"/templates/{template_id}?message=Approved templates cannot be edited. Please clone to create a new version.&message_type=error",
                status_code=303
            )
        
        return templates.TemplateResponse("template_form.html", {
            "request": request,
            "template": template,
            "variables": AVAILABLE_VARIABLES,
            "current_user": user,
            "users": users,
            "can_edit": can_edit_template(user),
            "can_approve": can_approve_template(user)
        })
    finally:
        db.close()


@router.post("/templates/{template_id}", response_class=HTMLResponse)
async def update_template_form(
    request: Request,
    template_id: int,
    name: str = Form(...),
    subject: str = Form(...),
    body_html: str = Form(...)
):
    user = get_user_from_cookie(request)
    
    db = SessionLocal()
    try:
        template = update_template(db, user, template_id, name, subject, body_html)
        db.commit()
        return RedirectResponse(
            url=f"/templates/{template_id}?message=Template updated successfully&message_type=success",
            status_code=303
        )
    except TemplateNotFoundError:
        return RedirectResponse(
            url="/templates?message=Template not found&message_type=error",
            status_code=303
        )
    except TemplatePermissionError as e:
        return RedirectResponse(
            url=f"/templates/{template_id}?message={str(e)}&message_type=error",
            status_code=303
        )
    except TemplateStateError as e:
        return RedirectResponse(
            url=f"/templates/{template_id}?message={str(e)}&message_type=error",
            status_code=303
        )
    finally:
        db.close()


@router.post("/templates/{template_id}/submit", response_class=HTMLResponse)
async def submit_template_form(request: Request, template_id: int):
    user = get_user_from_cookie(request)
    
    db = SessionLocal()
    try:
        submit_for_approval(db, user, template_id)
        db.commit()
        return RedirectResponse(
            url=f"/templates/{template_id}?message=Template submitted for approval&message_type=success",
            status_code=303
        )
    except TemplateNotFoundError:
        return RedirectResponse(
            url="/templates?message=Template not found&message_type=error",
            status_code=303
        )
    except (TemplatePermissionError, TemplateStateError) as e:
        return RedirectResponse(
            url=f"/templates/{template_id}?message={str(e)}&message_type=error",
            status_code=303
        )
    finally:
        db.close()


@router.post("/templates/{template_id}/approve", response_class=HTMLResponse)
async def approve_template_form(request: Request, template_id: int):
    user = get_user_from_cookie(request)
    
    db = SessionLocal()
    try:
        approve_template(db, user, template_id)
        db.commit()
        return RedirectResponse(
            url=f"/templates/{template_id}?message=Template approved successfully&message_type=success",
            status_code=303
        )
    except TemplateNotFoundError:
        return RedirectResponse(
            url="/templates?message=Template not found&message_type=error",
            status_code=303
        )
    except (TemplatePermissionError, TemplateStateError) as e:
        return RedirectResponse(
            url=f"/templates/{template_id}?message={str(e)}&message_type=error",
            status_code=303
        )
    finally:
        db.close()


@router.post("/templates/{template_id}/reject", response_class=HTMLResponse)
async def reject_template_form(
    request: Request,
    template_id: int,
    reason: str = Form(...)
):
    user = get_user_from_cookie(request)
    
    db = SessionLocal()
    try:
        reject_template(db, user, template_id, reason)
        db.commit()
        return RedirectResponse(
            url=f"/templates/{template_id}?message=Template rejected&message_type=warning",
            status_code=303
        )
    except TemplateNotFoundError:
        return RedirectResponse(
            url="/templates?message=Template not found&message_type=error",
            status_code=303
        )
    except (TemplatePermissionError, TemplateStateError) as e:
        return RedirectResponse(
            url=f"/templates/{template_id}?message={str(e)}&message_type=error",
            status_code=303
        )
    finally:
        db.close()


@router.post("/templates/{template_id}/clone", response_class=HTMLResponse)
async def clone_template_form(request: Request, template_id: int):
    user = get_user_from_cookie(request)
    
    db = SessionLocal()
    try:
        new_template = clone_template(db, user, template_id)
        db.commit()
        return RedirectResponse(
            url=f"/templates/{new_template.id}?message=Template cloned successfully. You can now edit this copy.&message_type=success",
            status_code=303
        )
    except TemplateNotFoundError:
        return RedirectResponse(
            url="/templates?message=Template not found&message_type=error",
            status_code=303
        )
    except TemplatePermissionError as e:
        return RedirectResponse(
            url=f"/templates/{template_id}?message={str(e)}&message_type=error",
            status_code=303
        )
    finally:
        db.close()
