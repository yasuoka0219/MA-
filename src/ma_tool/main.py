"""Main FastAPI application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

from src.ma_tool.api.endpoints import health, csv_import, unsubscribe, scheduler_api, tracking, templates, views
from src.ma_tool.config import settings

logger = logging.getLogger(__name__)

scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    
    logger.info(f"Starting MA Tool API in {settings.APP_ENV} environment")
    if settings.SENDGRID_API_KEY:
        try:
            settings.validate_required_for_email()
            logger.info("Email configuration validated successfully")
        except ValueError as e:
            logger.warning(f"Email configuration incomplete: {e}")
    else:
        logger.info("SendGrid not configured - email sending disabled")
    
    if settings.SCHEDULER_ENABLED:
        from src.ma_tool.services.scheduler import run_scheduler_tick
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            run_scheduler_tick,
            'interval',
            minutes=5,
            id='scenario_runner',
            replace_existing=True
        )
        scheduler.start()
        logger.info("Scheduler started - running every 5 minutes")
    
    yield
    
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
    logger.info("Shutting down MA Tool API")


app = FastAPI(
    title="MA Tool - University Marketing Automation",
    description="Marketing Automation tool for universities to manage student communications",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(health.router, tags=["Health"])
app.include_router(csv_import.router, tags=["Import"])
app.include_router(unsubscribe.router, tags=["Unsubscribe"])
app.include_router(scheduler_api.router, tags=["Scheduler"])
app.include_router(tracking.router, tags=["Tracking"])
app.include_router(templates.router, tags=["Templates"])
app.include_router(views.router)


@app.get("/")
def root():
    return {
        "message": "MA Tool API",
        "environment": settings.APP_ENV,
        "docs": "/docs"
    }
