"""UI Authentication endpoints - login/logout with session management"""
from typing import Optional
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from email_validator import validate_email, EmailNotValidError

from src.ma_tool.database import get_db
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.config import settings
from src.ma_tool.services.password import verify_password, hash_password
from src.ma_tool.services.password_reset import generate_password_reset_token, verify_password_reset_token
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.services.audit import log_action
from src.ma_tool.services.email import send_email

router = APIRouter(prefix="/ui", tags=["UI Auth"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: Optional[User] = None):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


def get_user_count(db: Session) -> int:
    """登録ユーザー数を返す（初回セットアップリンクの表示判定用）"""
    return db.execute(select(func.count()).select_from(User)).scalar() or 0


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    db: Session = Depends(get_db),
    error: Optional[str] = None,
):
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    
    user_count = get_user_count(db)
    return templates.TemplateResponse("login.html", {
        **get_base_context(request),
        "error": error,
        "show_setup_link": user_count == 0,
        "show_forgot_link": user_count > 0,
    })


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, db: Session = Depends(get_db)):
    """初回セットアップ画面（ユーザーが0人のときのみ表示）"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    if get_user_count(db) > 0:
        return RedirectResponse(url="/ui/login", status_code=302)
    return templates.TemplateResponse("ui_setup.html", {
        **get_base_context(request),
    })


@router.post("/setup")
async def setup_create(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    name: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    """初回セットアップ：最初の管理者を作成"""
    if get_user_count(db) > 0:
        return RedirectResponse(url="/ui/login", status_code=302)
    
    if password != password_confirm:
        return templates.TemplateResponse("ui_setup.html", {
            **get_base_context(request),
            "error": "パスワードと確認用が一致しません。",
            "email": email,
            "name": name,
        })
    
    if len(password) < 8:
        return templates.TemplateResponse("ui_setup.html", {
            **get_base_context(request),
            "error": "パスワードは8文字以上で設定してください。",
            "email": email,
            "name": name,
        })
    
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
        email = validated_email.email
    except EmailNotValidError as e:
        return templates.TemplateResponse("ui_setup.html", {
            **get_base_context(request),
            "error": f"メールアドレスの形式が不正です: {str(e)}",
            "email": email,
            "name": name,
        })
    
    new_user = User(
        email=email,
        name=name.strip(),
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return RedirectResponse(
        url="/ui/login?message=初回セットアップが完了しました。ログインしてください。",
        status_code=302,
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """パスワード再設定メール送信フォーム"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    return templates.TemplateResponse("ui_forgot_password.html", {
        **get_base_context(request),
    })


@router.post("/forgot-password")
async def forgot_password_send(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
):
    """登録メールアドレスにパスワード再設定リンクを送信（存在しないメールでも同じメッセージを表示）"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)

    email_clean = email.strip().lower()
    user = db.execute(
        select(User).where(User.email == email_clean, User.is_active == True)
    ).scalar_one_or_none()

    if user:
        token = generate_password_reset_token(user.id)
        reset_url = f"{settings.BASE_URL.rstrip('/')}/ui/reset-password?token={token}"
        subject = "【MA Tool】パスワード再設定のご案内"
        html_content = f"""
        <p>{user.name} 様</p>
        <p>MA Tool のパスワード再設定のリクエストを受け付けました。</p>
        <p>下記のリンクをクリックし、新しいパスワードを設定してください。</p>
        <p><a href="{reset_url}" style="word-break: break-all;">{reset_url}</a></p>
        <p>このリンクは1時間で無効になります。</p>
        <p>心当たりがない場合は、このメールを無視してください。</p>
        <hr>
        <p style="color:#666;font-size:12px;">MA Tool - 大学向けマーケティングオートメーション</p>
        """
        try:
            send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
            )
        except Exception:
            pass  # 送信失敗時も同じ画面を表示

    return templates.TemplateResponse("ui_forgot_password.html", {
        **get_base_context(request),
        "success": "ご入力いただいたメールアドレスにパスワード再設定用のリンクを送信しました。メールをご確認ください。（届かない場合は迷惑メールフォルダもご確認ください）",
    })


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: Optional[str] = None,
):
    """メール内リンクから遷移：新しいパスワード入力フォーム"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    if not token:
        return templates.TemplateResponse("ui_reset_password.html", {
            **get_base_context(request),
            "token_error": "リンクが正しくありません。",
            "token": "",
        })
    user_id = verify_password_reset_token(token)
    if not user_id:
        return templates.TemplateResponse("ui_reset_password.html", {
            **get_base_context(request),
            "token_error": "このリンクは無効か、有効期限が切れています。",
            "token": "",
        })
    return templates.TemplateResponse("ui_reset_password.html", {
        **get_base_context(request),
        "token": token,
    })


@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    """新しいパスワードで更新"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)

    user_id = verify_password_reset_token(token)
    if not user_id:
        return templates.TemplateResponse("ui_reset_password.html", {
            **get_base_context(request),
            "token_error": "このリンクは無効か、有効期限が切れています。",
            "token": "",
        })

    if password != password_confirm:
        return templates.TemplateResponse("ui_reset_password.html", {
            **get_base_context(request),
            "token": token,
            "error": "パスワードと確認用が一致しません。",
        })
    if len(password) < 8:
        return templates.TemplateResponse("ui_reset_password.html", {
            **get_base_context(request),
            "token": token,
            "error": "パスワードは8文字以上で設定してください。",
        })

    user = db.get(User, user_id)
    if not user or not user.is_active:
        return templates.TemplateResponse("ui_reset_password.html", {
            **get_base_context(request),
            "token_error": "ユーザーが見つからないか、無効です。",
            "token": "",
        })

    user.password_hash = hash_password(password)
    db.commit()

    return RedirectResponse(
        url="/ui/login?message=パスワードを変更しました。新しいパスワードでログインしてください。",
        status_code=302,
    )


@router.get("/forgot-login", response_class=HTMLResponse)
async def forgot_login_page(request: Request, db: Session = Depends(get_db)):
    """ログイン情報がわからない場合の案内ページ"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    user_count = get_user_count(db)
    return templates.TemplateResponse("ui_forgot_login.html", {
        **get_base_context(request),
        "show_setup_link": user_count == 0,
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
