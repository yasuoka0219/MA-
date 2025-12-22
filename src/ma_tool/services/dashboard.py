"""Dashboard service for email analytics"""
from datetime import datetime, timedelta, date, time
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import func, case, and_, select, cast, Date
from sqlalchemy.orm import Session

from src.ma_tool.models.send_log import SendLog, SendStatus
from src.ma_tool.models.lead import Lead
from src.ma_tool.models.scenario import Scenario

JST = ZoneInfo("Asia/Tokyo")


def get_daily_stats(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    days: int = 7
) -> List[Dict[str, Any]]:
    """
    Get daily email statistics for emails with status = SENT.
    Returns: sent_count, failed_count, opened_count, open_rate
    Uses JST timezone for date boundaries.
    """
    now_jst = datetime.now(JST)
    if end_date is None:
        end_date = now_jst.date()
    if start_date is None:
        start_date = end_date - timedelta(days=days - 1)
    
    results = []
    current = start_date
    
    while current <= end_date:
        next_day = current + timedelta(days=1)
        
        day_start = datetime.combine(current, time.min).replace(tzinfo=JST)
        day_end = datetime.combine(next_day, time.min).replace(tzinfo=JST)
        
        sent_query = db.execute(
            select(
                func.count(SendLog.id).label("sent"),
                func.sum(case((SendLog.opened_at.isnot(None), 1), else_=0)).label("opened")
            ).where(
                and_(
                    SendLog.status == SendStatus.SENT,
                    SendLog.sent_at >= day_start,
                    SendLog.sent_at < day_end
                )
            )
        ).first()
        
        failed_query = db.execute(
            select(func.count(SendLog.id)).where(
                and_(
                    SendLog.status == SendStatus.FAILED,
                    SendLog.created_at >= day_start,
                    SendLog.created_at < day_end
                )
            )
        ).scalar() or 0
        
        sent = sent_query.sent or 0
        opened = sent_query.opened or 0
        failed = failed_query
        open_rate = (opened / sent * 100) if sent > 0 else 0.0
        
        results.append({
            "date": current.isoformat(),
            "sent": sent,
            "failed": failed,
            "opened": opened,
            "open_rate": round(open_rate, 1)
        })
        
        current = next_day
    
    return results


def get_graduation_year_stats(db: Session) -> List[Dict[str, Any]]:
    """
    Get open rate statistics by graduation year.
    Returns: graduation_year, sent_count, opened_count, open_rate (sorted by open_rate desc)
    """
    stats = db.execute(
        select(
            Lead.graduation_year,
            func.count(SendLog.id).label("sent"),
            func.sum(case((SendLog.opened_at.isnot(None), 1), else_=0)).label("opened")
        ).join(
            Lead, SendLog.lead_id == Lead.id
        ).where(
            SendLog.status == SendStatus.SENT
        ).group_by(
            Lead.graduation_year
        ).order_by(
            Lead.graduation_year.desc()
        )
    ).all()
    
    results = []
    for row in stats:
        sent = row.sent or 0
        opened = row.opened or 0
        open_rate = (opened / sent * 100) if sent > 0 else 0.0
        
        results.append({
            "graduation_year": row.graduation_year,
            "sent": sent,
            "opened": opened,
            "open_rate": round(open_rate, 1)
        })
    
    results.sort(key=lambda x: x["open_rate"], reverse=True)
    
    return results


def get_scenario_stats(db: Session) -> List[Dict[str, Any]]:
    """
    Get statistics by scenario.
    Returns: scenario_id, scenario_name, sent_count, opened_count, open_rate
    """
    stats = db.execute(
        select(
            Scenario.id,
            Scenario.name,
            func.count(SendLog.id).label("sent"),
            func.sum(case((SendLog.opened_at.isnot(None), 1), else_=0)).label("opened")
        ).join(
            Scenario, SendLog.scenario_id == Scenario.id
        ).where(
            SendLog.status == SendStatus.SENT
        ).group_by(
            Scenario.id, Scenario.name
        )
    ).all()
    
    results = []
    for row in stats:
        sent = row.sent or 0
        opened = row.opened or 0
        open_rate = (opened / sent * 100) if sent > 0 else 0.0
        
        results.append({
            "scenario_id": row.id,
            "scenario_name": row.name,
            "sent": sent,
            "opened": opened,
            "open_rate": round(open_rate, 1)
        })
    
    results.sort(key=lambda x: x["open_rate"], reverse=True)
    
    return results


def get_summary_stats(db: Session) -> Dict[str, Any]:
    """
    Get overall summary statistics.
    """
    stats = db.execute(
        select(
            func.count(SendLog.id).label("total"),
            func.sum(case((SendLog.status == SendStatus.SENT, 1), else_=0)).label("sent"),
            func.sum(case((SendLog.status == SendStatus.FAILED, 1), else_=0)).label("failed"),
            func.sum(case((SendLog.status == SendStatus.SCHEDULED, 1), else_=0)).label("scheduled"),
            func.sum(case((SendLog.opened_at.isnot(None), 1), else_=0)).label("opened")
        )
    ).first()
    
    total = stats.total or 0
    sent = stats.sent or 0
    failed = stats.failed or 0
    scheduled = stats.scheduled or 0
    opened = stats.opened or 0
    open_rate = (opened / sent * 100) if sent > 0 else 0.0
    
    return {
        "total": total,
        "sent": sent,
        "failed": failed,
        "scheduled": scheduled,
        "opened": opened,
        "open_rate": round(open_rate, 1)
    }
