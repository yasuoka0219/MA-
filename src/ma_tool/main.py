"""Main FastAPI application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.ma_tool.api.endpoints import health, csv_import, unsubscribe
from src.ma_tool.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting MA Tool API in {settings.APP_ENV} environment")
    if settings.SENDGRID_API_KEY:
        try:
            settings.validate_required_for_email()
            logger.info("Email configuration validated successfully")
        except ValueError as e:
            logger.warning(f"Email configuration incomplete: {e}")
    else:
        logger.info("SendGrid not configured - email sending disabled")
    yield
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


@app.get("/")
def root():
    return {
        "message": "MA Tool API",
        "environment": settings.APP_ENV,
        "docs": "/docs"
    }
