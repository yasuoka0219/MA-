"""UI endpoints for user management"""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from email_validator import validate_email, EmailNotValidError

from src.ma_tool.database import get_db
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings
from src.ma_tool.services.audit import log_action
from src.ma_tool.services.password import hash_password

router = APIRouter(prefix="/ui", tags=["UI Users"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    role_filter: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
):
    """ユーザー一覧を表示（adminのみ）"""
    if not is_admin(user):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    
    query = select(User).order_by(User.created_at.desc())
    
    if role_filter:
        try:
            role = UserRole(role_filter)
            query = query.where(User.role == role)
        except ValueError:
            pass
    
    users = db.execute(query).scalars().all()
    
    return templates.TemplateResponse("ui_users_list.html", {
        **get_base_context(request, user),
        "users": users,
        "role_filter": role_filter or "",
        "roles": [r.value for r in UserRole],
        "message": message,
    })


@router.get("/users/new", response_class=HTMLResponse)
async def user_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """新規ユーザー作成フォーム（adminのみ）"""
    if not is_admin(user):
        return RedirectResponse(url="/ui/users", status_code=302)
    
    return templates.TemplateResponse("ui_user_form.html", {
        **get_base_context(request, user),
        "target_user": None,
        "is_new": True,
        "roles": [r.value for r in UserRole],
    })


@router.post("/users/new")
async def user_create(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """新規ユーザーを作成（adminのみ）"""
    if not is_admin(user):
        return RedirectResponse(url="/ui/users", status_code=302)
    
    # メールアドレスのバリデーション
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
        email = validated_email.email
    except EmailNotValidError as e:
        return templates.TemplateResponse("ui_user_form.html", {
            **get_base_context(request, user),
            "target_user": None,
            "is_new": True,
            "roles": [r.value for r in UserRole],
            "error": f"メールアドレスの形式が不正です: {str(e)}",
            "form_data": {
                "email": email,
                "name": name,
                "role": role,
                "is_active": is_active,
            }
        })
    
    # メールアドレスの重複チェック
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        return templates.TemplateResponse("ui_user_form.html", {
            **get_base_context(request, user),
            "target_user": None,
            "is_new": True,
            "roles": [r.value for r in UserRole],
            "error": f"このメールアドレスは既に登録されています（ID: {existing.id}）",
            "form_data": {
                "email": email,
                "name": name,
                "role": role,
                "is_active": is_active,
            }
        })
    
    # パスワードのバリデーション
    if len(password) < 8:
        return templates.TemplateResponse("ui_user_form.html", {
            **get_base_context(request, user),
            "target_user": None,
            "is_new": True,
            "roles": [r.value for r in UserRole],
            "error": "パスワードは8文字以上である必要があります",
            "form_data": {
                "email": email,
                "name": name,
                "role": role,
                "is_active": is_active,
            }
        })
    
    # ロールのバリデーション
    try:
        user_role = UserRole(role)
    except ValueError:
        return templates.TemplateResponse("ui_user_form.html", {
            **get_base_context(request, user),
            "target_user": None,
            "is_new": True,
            "roles": [r.value for r in UserRole],
            "error": f"無効なロールです: {role}",
            "form_data": {
                "email": email,
                "name": name,
                "role": role,
                "is_active": is_active,
            }
        })
    
    # パスワードをハッシュ化
    password_hash = hash_password(password)
    
    new_user = User(
        email=email,
        name=name.strip(),
        password_hash=password_hash,
        role=user_role,
        is_active=is_active,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    log_action(
        db=db,
        actor=user,
        action="USER_CREATED",
        target_type="user",
        target_id=new_user.id,
        meta={"email": new_user.email, "role": new_user.role.value}
    )
    
    response = RedirectResponse(url=f"/ui/users?message=ユーザーを登録しました", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "ユーザーを登録しました", "type": "success"}})
    return response


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def user_edit(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """ユーザー編集フォーム（adminのみ）"""
    if not is_admin(user):
        return RedirectResponse(url="/ui/users", status_code=302)
    
    target_user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target_user:
        return HTMLResponse("<h1>ユーザーが見つかりません</h1>", status_code=404)
    
    return templates.TemplateResponse("ui_user_form.html", {
        **get_base_context(request, user),
        "target_user": target_user,
        "is_new": False,
        "roles": [r.value for r in UserRole],
    })


@router.post("/users/{user_id}/edit")
async def user_update(
    request: Request,
    user_id: int,
    email: str = Form(...),
    name: str = Form(...),
    password: Optional[str] = Form(None),
    role: str = Form(...),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """ユーザーを更新（adminのみ）"""
    if not is_admin(user):
        return RedirectResponse(url=f"/ui/users/{user_id}/edit", status_code=302)
    
    target_user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target_user:
        return RedirectResponse(url="/ui/users", status_code=302)
    
    # メールアドレスのバリデーション
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
        email = validated_email.email
    except EmailNotValidError as e:
        return templates.TemplateResponse("ui_user_form.html", {
            **get_base_context(request, user),
            "target_user": target_user,
            "is_new": False,
            "roles": [r.value for r in UserRole],
            "error": f"メールアドレスの形式が不正です: {str(e)}",
        })
    
    # メールアドレスの重複チェック（自分以外）
    existing = db.execute(select(User).where(User.email == email, User.id != user_id)).scalar_one_or_none()
    if existing:
        return templates.TemplateResponse("ui_user_form.html", {
            **get_base_context(request, user),
            "target_user": target_user,
            "is_new": False,
            "roles": [r.value for r in UserRole],
            "error": f"このメールアドレスは既に登録されています（ID: {existing.id}）",
        })
    
    # パスワードのバリデーション（変更する場合のみ）
    if password:
        if len(password) < 8:
            return templates.TemplateResponse("ui_user_form.html", {
                **get_base_context(request, user),
                "target_user": target_user,
                "is_new": False,
                "roles": [r.value for r in UserRole],
                "error": "パスワードは8文字以上である必要があります",
            })
        # パスワードをハッシュ化して更新
        target_user.password_hash = hash_password(password)
    
    # ロールのバリデーション
    try:
        user_role = UserRole(role)
    except ValueError:
        return templates.TemplateResponse("ui_user_form.html", {
            **get_base_context(request, user),
            "target_user": target_user,
            "is_new": False,
            "roles": [r.value for r in UserRole],
            "error": f"無効なロールです: {role}",
        })
    
    old_role = target_user.role.value
    target_user.email = email
    target_user.name = name.strip()
    target_user.role = user_role
    target_user.is_active = is_active
    db.commit()
    
    log_action(
        db=db,
        actor=user,
        action="USER_UPDATED",
        target_type="user",
        target_id=target_user.id,
        meta={
            "email": target_user.email,
            "old_role": old_role,
            "new_role": target_user.role.value,
            "is_active": is_active
        }
    )
    
    response = RedirectResponse(url=f"/ui/users?message=ユーザーを更新しました", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "ユーザーを更新しました", "type": "success"}})
    return response


@router.post("/users/{user_id}/delete")
async def user_delete(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """ユーザーを削除（adminのみ、自分自身は削除不可）"""
    if not is_admin(user):
        return HTMLResponse("<div class='alert alert-danger'>権限がありません</div>", status_code=403)
    
    target_user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target_user:
        return HTMLResponse("<div class='alert alert-danger'>ユーザーが見つかりません</div>", status_code=404)
    
    # 自分自身は削除不可
    if target_user.id == user.id:
        return HTMLResponse("<div class='alert alert-danger'>自分自身を削除することはできません</div>", status_code=400)
    
    # 論理削除（is_activeをFalseにする）
    target_user.is_active = False
    db.commit()
    
    log_action(
        db=db,
        actor=user,
        action="USER_DELETED",
        target_type="user",
        target_id=target_user.id,
        meta={"email": target_user.email, "role": target_user.role.value}
    )
    
    response = RedirectResponse(url="/ui/users?message=ユーザーを削除しました", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "ユーザーを削除しました", "type": "success"}})
    return response
