"""Dashboard API and UI endpoints"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from src.ma_tool.database import SessionLocal
from src.ma_tool.models.user import User
from src.ma_tool.services.dashboard import (
    get_daily_stats, get_graduation_year_stats,
    get_scenario_stats, get_summary_stats
)
from src.ma_tool.api.deps import can_edit_template, can_approve_template

router = APIRouter(tags=["Dashboard"])
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


@router.get("/api/dashboard/summary")
def api_summary():
    """Get overall summary statistics"""
    db = SessionLocal()
    try:
        return get_summary_stats(db)
    finally:
        db.close()


@router.get("/api/dashboard/daily")
def api_daily_stats(
    days: int = Query(7, ge=1, le=90),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    """Get daily statistics"""
    db = SessionLocal()
    try:
        return get_daily_stats(db, start_date=start_date, end_date=end_date, days=days)
    finally:
        db.close()


@router.get("/api/dashboard/graduation-year")
def api_graduation_year_stats():
    """Get statistics by graduation year"""
    db = SessionLocal()
    try:
        return get_graduation_year_stats(db)
    finally:
        db.close()


@router.get("/api/dashboard/scenario")
def api_scenario_stats():
    """Get statistics by scenario"""
    db = SessionLocal()
    try:
        return get_scenario_stats(db)
    finally:
        db.close()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    days: int = Query(7, ge=1, le=90)
):
    """Dashboard UI"""
    user = get_user_from_cookie(request)
    users = get_all_users()
    
    db = SessionLocal()
    try:
        summary = get_summary_stats(db)
        daily = get_daily_stats(db, days=days)
        by_graduation_year = get_graduation_year_stats(db)
        by_scenario = get_scenario_stats(db)
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "summary": summary,
            "daily": daily,
            "by_graduation_year": by_graduation_year,
            "by_scenario": by_scenario,
            "days": days,
            "current_user": user,
            "users": users,
            "can_edit": can_edit_template(user),
            "can_approve": can_approve_template(user)
        })
    finally:
        db.close()
