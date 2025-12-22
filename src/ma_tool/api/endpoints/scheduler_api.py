"""Scheduler management endpoints for testing and monitoring"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from src.ma_tool.database import get_db
from src.ma_tool.models.send_log import SendLog, SendStatus
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.services.scheduler import run_scheduler_tick
from src.ma_tool.api.deps import require_admin

router = APIRouter(prefix="/scheduler")

JST = ZoneInfo("Asia/Tokyo")


@router.post("/trigger")
def trigger_scheduler_tick(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    run_scheduler_tick()
    return {"message": "Scheduler tick executed", "timestamp": datetime.now(JST).isoformat()}


@router.get("/status")
def get_scheduler_status(db: Session = Depends(get_db)):
    now = datetime.now(JST)
    
    pending_count = db.execute(
        select(func.count()).select_from(SendLog).where(SendLog.status == SendStatus.SCHEDULED)
    ).scalar()
    
    sent_count = db.execute(
        select(func.count()).select_from(SendLog).where(SendLog.status == SendStatus.SENT)
    ).scalar()
    
    failed_count = db.execute(
        select(func.count()).select_from(SendLog).where(SendLog.status == SendStatus.FAILED)
    ).scalar()
    
    active_scenarios = db.execute(
        select(func.count()).select_from(Scenario).where(Scenario.is_enabled == True)
    ).scalar()
    
    return {
        "current_time_jst": now.isoformat(),
        "send_logs": {
            "pending": pending_count,
            "sent": sent_count,
            "failed": failed_count
        },
        "active_scenarios": active_scenarios
    }


@router.get("/pending")
def get_pending_sends(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    now = datetime.now(JST)
    
    stmt = select(SendLog).where(
        SendLog.status == SendStatus.SCHEDULED
    ).order_by(SendLog.scheduled_for).limit(limit)
    
    logs = list(db.execute(stmt).scalars().all())
    
    return {
        "count": len(logs),
        "items": [
            {
                "id": log.id,
                "lead_id": log.lead_id,
                "scenario_id": log.scenario_id,
                "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
                "is_due": log.scheduled_for <= now if log.scheduled_for else False,
                "attempt_count": log.attempt_count
            }
            for log in logs
        ]
    }
