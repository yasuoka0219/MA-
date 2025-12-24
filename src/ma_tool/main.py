"""Main FastAPI application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from src.ma_tool.api.endpoints import health, csv_import, unsubscribe, scheduler_api, tracking, templates, views, dashboard, line_webhook
from src.ma_tool.api.endpoints import ui_auth, ui_leads, ui_line, ui_templates, ui_scenarios, ui_sendlogs
from src.ma_tool.config import settings

logger = logging.getLogger(__name__)

if not settings.SESSION_SECRET_KEY:
    raise RuntimeError("SESSION_SECRET_KEY environment variable is required")

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

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    session_cookie="ma_session",
    max_age=60 * 60 * 24 * 7,
)

app.include_router(health.router, tags=["Health"])
app.include_router(csv_import.router, tags=["Import"])
app.include_router(unsubscribe.router, tags=["Unsubscribe"])
app.include_router(scheduler_api.router, tags=["Scheduler"])
app.include_router(tracking.router, tags=["Tracking"])
app.include_router(templates.router, tags=["Templates"])
app.include_router(views.router)
app.include_router(dashboard.router)
app.include_router(line_webhook.router)

app.include_router(ui_auth.router)
app.include_router(ui_leads.router)
app.include_router(ui_line.router)
app.include_router(ui_templates.router)
app.include_router(ui_scenarios.router)
app.include_router(ui_sendlogs.router)


@app.get("/")
def root():
    return {
        "message": "MA Tool API",
        "environment": settings.APP_ENV,
        "docs": "/docs"
    }
