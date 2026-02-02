"""UI endpoints for template management (LINE-focused)"""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import get_db
from src.ma_tool.models.template import Template, TemplateStatus, ChannelType
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.models.audit_log import AuditLog
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings
from src.ma_tool.services.line import get_line_service, LineMessage

router = APIRouter(prefix="/ui", tags=["UI Templates"])
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


def can_edit(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.EDITOR]


def can_approve(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.APPROVER]


@router.get("/templates", response_class=HTMLResponse)
async def templates_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    status_filter: Optional[str] = Query(None),
    channel_filter: Optional[str] = Query(None),
):
    query = select(Template)
    
    if status_filter:
        try:
            status = TemplateStatus(status_filter)
            query = query.where(Template.status == status)
        except ValueError:
            pass
    
    if channel_filter:
        try:
            channel = ChannelType(channel_filter)
            query = query.where(Template.channel_type == channel)
        except ValueError:
            pass
    
    query = query.order_by(Template.updated_at.desc())
    template_list = db.execute(query).scalars().all()
    
    status_counts = {
        "all": db.execute(select(Template)).scalars().all().__len__(),
        "draft": db.execute(select(Template).where(Template.status == TemplateStatus.DRAFT)).scalars().all().__len__(),
        "pending": db.execute(select(Template).where(Template.status == TemplateStatus.PENDING)).scalars().all().__len__(),
        "approved": db.execute(select(Template).where(Template.status == TemplateStatus.APPROVED)).scalars().all().__len__(),
        "rejected": db.execute(select(Template).where(Template.status == TemplateStatus.REJECTED)).scalars().all().__len__(),
    }
    
    return templates.TemplateResponse("ui_templates_list.html", {
        **get_base_context(request, user),
        "templates": template_list,
        "status_filter": status_filter or "",
        "channel_filter": channel_filter or "",
        "status_counts": status_counts,
        "can_edit": can_edit(user),
        "can_approve": can_approve(user),
    })


@router.get("/templates/new", response_class=HTMLResponse)
async def template_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/templates", status_code=302)
    
    return templates.TemplateResponse("ui_template_form.html", {
        **get_base_context(request, user),
        "template": None,
        "is_new": True,
        "flex_json_str": "",
    })


@router.post("/templates/new")
async def template_create(
    request: Request,
    name: str = Form(...),
    channel_type: str = Form(...),
    subject: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    message_text: Optional[str] = Form(None),
    flex_message_json: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url="/ui/templates", status_code=302)
    
    try:
        channel = ChannelType(channel_type)
    except ValueError:
        channel = ChannelType.EMAIL
    
    flex_json = None
    if flex_message_json and flex_message_json.strip():
        try:
            flex_json = json.loads(flex_message_json.strip())
            # Flex Messageの基本構造をチェック
            if not isinstance(flex_json, dict):
                raise ValueError("Flex Message JSONはオブジェクトである必要があります")
        except json.JSONDecodeError as e:
            error_msg = f"Flex Message JSONの形式が不正です: {str(e)}"
            response = Response(
                content=f"<div class='alert alert-danger'>{error_msg}</div>",
                media_type="text/html"
            )
            response.headers["HX-Trigger"] = json.dumps({
                "showToast": {"type": "danger", "message": error_msg}
            })
            return response
        except ValueError as e:
            error_msg = f"Flex Message JSONの形式が不正です: {str(e)}"
            response = Response(
                content=f"<div class='alert alert-danger'>{error_msg}</div>",
                media_type="text/html"
            )
            response.headers["HX-Trigger"] = json.dumps({
                "showToast": {"type": "danger", "message": error_msg}
            })
            return response
    
    template = Template(
        name=name,
        channel_type=channel,
        subject=subject or "",
        body_html=body or "",
        message_text=message_text,
        flex_message_json=flex_json,
        status=TemplateStatus.DRAFT,
        created_by=user.id,
    )
    db.add(template)
    db.commit()
    
    create_audit_log(db, user, "create", "template", template.id, {"name": name, "channel": channel.value})
    
    return RedirectResponse(url=f"/ui/templates/{template.id}", status_code=302)


@router.get("/templates/{template_id}", response_class=HTMLResponse)
async def template_detail(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    template = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not template:
        return HTMLResponse("<h1>テンプレートが見つかりません</h1>", status_code=404)
    
    return templates.TemplateResponse("ui_template_detail.html", {
        **get_base_context(request, user),
        "template": template,
        "can_edit": can_edit(user) and template.status != TemplateStatus.APPROVED,
        "can_submit": can_edit(user) and template.status == TemplateStatus.DRAFT,
        "can_approve": can_approve(user) and template.status == TemplateStatus.PENDING,
        "can_test_send": not settings.is_production and template.channel_type == ChannelType.LINE,
    })


@router.get("/templates/{template_id}/edit", response_class=HTMLResponse)
async def template_edit(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/templates/{template_id}", status_code=302)
    
    template = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not template:
        return HTMLResponse("<h1>テンプレートが見つかりません</h1>", status_code=404)
    
    if template.status == TemplateStatus.APPROVED:
        return RedirectResponse(url=f"/ui/templates/{template_id}", status_code=302)
    
    # Flex Message JSONを文字列に変換
    flex_json_str = ""
    if template.flex_message_json:
        flex_json_str = json.dumps(template.flex_message_json, ensure_ascii=False, indent=2)
    
    return templates.TemplateResponse("ui_template_form.html", {
        **get_base_context(request, user),
        "template": template,
        "is_new": False,
        "flex_json_str": flex_json_str,
    })


@router.post("/templates/{template_id}/edit")
async def template_update(
    request: Request,
    template_id: int,
    name: str = Form(...),
    channel_type: str = Form(...),
    subject: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    message_text: Optional[str] = Form(None),
    flex_message_json: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/templates/{template_id}", status_code=302)
    
    template = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not template or template.status == TemplateStatus.APPROVED:
        return RedirectResponse(url=f"/ui/templates/{template_id}", status_code=302)
    
    flex_json = None
    if flex_message_json and flex_message_json.strip():
        try:
            flex_json = json.loads(flex_message_json.strip())
            # Flex Messageの基本構造をチェック
            if not isinstance(flex_json, dict):
                raise ValueError("Flex Message JSONはオブジェクトである必要があります")
        except json.JSONDecodeError as e:
            error_msg = f"Flex Message JSONの形式が不正です: {str(e)}"
            response = Response(
                content=f"<div class='alert alert-danger'>{error_msg}</div>",
                media_type="text/html"
            )
            response.headers["HX-Trigger"] = json.dumps({
                "showToast": {"type": "danger", "message": error_msg}
            })
            return response
        except ValueError as e:
            error_msg = f"Flex Message JSONの形式が不正です: {str(e)}"
            response = Response(
                content=f"<div class='alert alert-danger'>{error_msg}</div>",
                media_type="text/html"
            )
            response.headers["HX-Trigger"] = json.dumps({
                "showToast": {"type": "danger", "message": error_msg}
            })
            return response
    
    template.name = name
    template.channel_type = ChannelType(channel_type)
    template.subject = subject or ""
    template.body_html = body or ""
    template.message_text = message_text
    template.flex_message_json = flex_json
    template.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    create_audit_log(db, user, "update", "template", template_id)
    
    return RedirectResponse(url=f"/ui/templates/{template_id}", status_code=302)


@router.post("/templates/{template_id}/submit", response_class=HTMLResponse)
async def template_submit(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    template = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not template or template.status != TemplateStatus.DRAFT:
        return Response(
            content="<span class='badge bg-secondary'>変更不可</span>",
            media_type="text/html"
        )
    
    template.status = TemplateStatus.PENDING
    template.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(template)
    
    create_audit_log(db, user, "submit", "template", template_id)
    
    # ページ全体をリロードするためにHTMXイベントを使用
    response = Response(
        content="<span class='badge bg-warning fs-6'>承認待ち</span>",
        media_type="text/html"
    )
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "承認申請しました", "type": "success"},
        "refreshPage": True
    })
    return response


@router.post("/templates/{template_id}/approve", response_class=HTMLResponse)
async def template_approve(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_approve(user):
        return Response(content="<span class='badge bg-danger'>権限不足</span>", media_type="text/html")
    
    template = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not template or template.status != TemplateStatus.PENDING:
        return Response(content="<span class='badge bg-secondary'>変更不可</span>", media_type="text/html")
    
    template.status = TemplateStatus.APPROVED
    template.approved_at = datetime.now(timezone.utc)
    template.approved_by = user.id
    db.commit()
    db.refresh(template)
    
    create_audit_log(db, user, "approve", "template", template_id)
    
    # ページ全体をリロードするためにHTMXイベントを使用
    response = Response(
        content="<span class='badge bg-success fs-6'>承認済み</span>",
        media_type="text/html"
    )
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "承認しました", "type": "success"},
        "refreshPage": True
    })
    return response


@router.post("/templates/{template_id}/reject", response_class=HTMLResponse)
async def template_reject(
    request: Request,
    template_id: int,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_approve(user):
        return Response(content="<span class='badge bg-danger'>権限不足</span>", media_type="text/html")
    
    template = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not template or template.status != TemplateStatus.PENDING:
        return Response(content="<span class='badge bg-secondary'>変更不可</span>", media_type="text/html")
    
    template.status = TemplateStatus.REJECTED
    template.rejected_reason = reason
    template.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(template)
    
    create_audit_log(db, user, "reject", "template", template_id, {"reason": reason})
    
    # ページ全体をリロードするためにHTMXイベントを使用
    response = Response(
        content="<span class='badge bg-danger fs-6'>却下</span>",
        media_type="text/html"
    )
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "却下しました", "type": "warning"},
        "refreshPage": True
    })
    return response


@router.post("/templates/{template_id}/clone")
async def template_clone(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if not can_edit(user):
        return RedirectResponse(url=f"/ui/templates/{template_id}", status_code=302)
    
    original = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not original:
        return RedirectResponse(url="/ui/templates", status_code=302)
    
    new_template = Template(
        name=f"{original.name} (コピー)",
        channel_type=original.channel_type,
        subject=original.subject,
        body_html=original.body_html,
        message_text=original.message_text,
        flex_message_json=original.flex_message_json,
        status=TemplateStatus.DRAFT,
        created_by=user.id,
    )
    db.add(new_template)
    db.commit()
    
    create_audit_log(db, user, "clone", "template", new_template.id, {"original_id": template_id})
    
    return RedirectResponse(url=f"/ui/templates/{new_template.id}", status_code=302)


@router.post("/templates/{template_id}/test-send", response_class=HTMLResponse)
async def template_test_send(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    if settings.is_production:
        return Response(
            content="<div class='alert alert-danger'>本番環境ではテスト送信できません</div>",
            media_type="text/html"
        )
    
    template = db.execute(select(Template).where(Template.id == template_id)).scalar_one_or_none()
    if not template or template.channel_type != ChannelType.LINE:
        return Response(
            content="<div class='alert alert-danger'>LINEテンプレートのみテスト送信可能です</div>",
            media_type="text/html"
        )
    
    if not settings.LINE_TEST_USER_ID:
        return Response(
            content="<div class='alert alert-warning'>LINE_TEST_USER_IDが設定されていません</div>",
            media_type="text/html"
        )
    
    try:
        line_service = get_line_service()
        
        flex_msg = template.flex_message_json
        
        message = LineMessage(
            to_user_id=settings.LINE_TEST_USER_ID,
            text=template.message_text,
            flex_message=flex_msg,
            alt_text=template.name,
        )
        
        result = line_service.send(message)
        
        create_audit_log(db, user, "test_send", "template", template_id, {
            "channel": "line",
            "success": result.success,
            "status": result.status,
        })
        
        if result.success:
            return Response(
                content=f"<div class='alert alert-success'>テスト送信成功 (to: {settings.LINE_TEST_USER_ID[:10]}...)</div>",
                media_type="text/html"
            )
        else:
            return Response(
                content=f"<div class='alert alert-danger'>送信失敗: {result.message}</div>",
                media_type="text/html"
            )
    except Exception as e:
        return Response(
            content=f"<div class='alert alert-danger'>エラー: {str(e)}</div>",
            media_type="text/html"
        )
