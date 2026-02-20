"""Main FastAPI application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from src.ma_tool.api.endpoints import health, csv_import, unsubscribe, scheduler_api, tracking, sendgrid_webhook, templates, views, dashboard, line_webhook
from src.ma_tool.api.endpoints import ui_auth, ui_leads, ui_leads_hot, ui_line, ui_templates, ui_scenarios, ui_sendlogs, ui_import, ui_dashboard, ui_events, ui_audit_logs, ui_users
from src.ma_tool.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
app.include_router(sendgrid_webhook.router, tags=["Webhooks"])
app.include_router(templates.router, tags=["Templates"])
app.include_router(views.router)
app.include_router(dashboard.router)
app.include_router(line_webhook.router)

app.include_router(ui_auth.router)
app.include_router(ui_dashboard.router)
app.include_router(ui_leads_hot.router)
app.include_router(ui_leads.router)
app.include_router(ui_line.router)
app.include_router(ui_templates.router)
app.include_router(ui_scenarios.router)
app.include_router(ui_sendlogs.router)
app.include_router(ui_import.router)
app.include_router(ui_events.router)
app.include_router(ui_audit_logs.router)
app.include_router(ui_users.router)


@app.get("/")
async def root(request: Request):
    """Root redirect - login or dashboard based on session"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login")
async def login_shortcut(request: Request):
    """Shortcut to /ui/login"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    return RedirectResponse(url="/ui/login", status_code=302)


@app.get("/logout")
async def logout_shortcut(request: Request):
    """Shortcut to /ui/logout"""
    return RedirectResponse(url="/ui/logout", status_code=302)


@app.on_event("startup")
async def log_routes():
    """Log all registered routes on startup"""
    logger.info("=" * 60)
    logger.info("REGISTERED ROUTES:")
    logger.info("=" * 60)
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = ", ".join(route.methods - {"HEAD", "OPTIONS"})
            if methods:
                logger.info(f"  {methods:20} {route.path}")
    logger.info("=" * 60)
