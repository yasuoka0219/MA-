"""UI Authentication endpoints - login/logout with session management"""
from typing import Optional
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import get_db
from src.ma_tool.models.user import User
from src.ma_tool.config import settings
from src.ma_tool.services.password import verify_password, hash_password
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.services.audit import log_action

router = APIRouter(prefix="/ui", tags=["UI Auth"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: Optional[User] = None):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    
    return templates.TemplateResponse("login.html", {
        **get_base_context(request),
        "error": error,
    })


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.execute(
        select(User).where(User.email == email.lower().strip(), User.is_active == True)
    ).scalar_one_or_none()
    
    if not user:
        return templates.TemplateResponse("login.html", {
            **get_base_context(request),
            "error": "メールアドレスまたはパスワードが正しくありません",
            "email": email,
        })
    
    # パスワード検証
    if not user.password_hash:
        return templates.TemplateResponse("login.html", {
            **get_base_context(request),
            "error": "パスワードが設定されていません。管理者に連絡してください。",
            "email": email,
        })
    
    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            **get_base_context(request),
            "error": "メールアドレスまたはパスワードが正しくありません",
            "email": email,
        })
    
    request.session["user_id"] = user.id
    request.session["user_role"] = user.role.value
    
    return RedirectResponse(url="/ui/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/ui/login", status_code=302)


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    error: Optional[str] = None,
    success: Optional[str] = None,
):
    """パスワード変更ページ"""
    return templates.TemplateResponse("ui_change_password.html", {
        **get_base_context(request, user),
        "error": error,
        "success": success,
    })


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """パスワード変更処理"""
    # 現在のパスワード確認
    if not user.password_hash:
        return templates.TemplateResponse("ui_change_password.html", {
            **get_base_context(request, user),
            "error": "パスワードが設定されていません。管理者に連絡してください。",
        })
    
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse("ui_change_password.html", {
            **get_base_context(request, user),
            "error": "現在のパスワードが正しくありません。",
        })
    
    # 新パスワードのバリデーション
    if len(new_password) < 8:
        return templates.TemplateResponse("ui_change_password.html", {
            **get_base_context(request, user),
            "error": "新しいパスワードは8文字以上である必要があります。",
        })
    
    if new_password != confirm_password:
        return templates.TemplateResponse("ui_change_password.html", {
            **get_base_context(request, user),
            "error": "新しいパスワードと確認用パスワードが一致しません。",
        })
    
    # 現在のパスワードと同じかチェック
    if verify_password(new_password, user.password_hash):
        return templates.TemplateResponse("ui_change_password.html", {
            **get_base_context(request, user),
            "error": "新しいパスワードは現在のパスワードと異なる必要があります。",
        })
    
    # パスワードを更新
    user.password_hash = hash_password(new_password)
    db.commit()
    
    # 監査ログ記録
    log_action(
        db=db,
        actor=user,
        action="PASSWORD_CHANGED",
        target_type="user",
        target_id=user.id,
        meta={}
    )
    
    return templates.TemplateResponse("ui_change_password.html", {
        **get_base_context(request, user),
        "success": "パスワードを変更しました。",
    })
