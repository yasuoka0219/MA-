"""Health check endpoint"""
from fastapi import APIRouter
from sqlalchemy import text

from src.ma_tool.database import SessionLocal
from src.ma_tool.config import settings

router = APIRouter()


@router.get("/health")
def health_check():
    db_status = "unknown"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "ok",
        "environment": settings.APP_ENV,
        "database": db_status
    }
