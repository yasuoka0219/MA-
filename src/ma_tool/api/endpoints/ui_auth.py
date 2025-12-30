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
    db: Session = Depends(get_db)
):
    user = db.execute(
        select(User).where(User.email == email.lower().strip(), User.is_active == True)
    ).scalar_one_or_none()
    
    if not user:
        return templates.TemplateResponse("login.html", {
            **get_base_context(request),
            "error": "このメールアドレスは登録されていません",
            "email": email,
        })
    
    request.session["user_id"] = user.id
    request.session["user_role"] = user.role.value
    
    return RedirectResponse(url="/ui/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/ui/login", status_code=302)
