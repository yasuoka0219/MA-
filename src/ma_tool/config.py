"""Application settings using Pydantic Settings"""
from typing import Optional, List
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    
    SENDGRID_API_KEY: str = ""
    
    APP_ENV: str = "dev"
    
    MAIL_FROM: str = "noreply@example.com"
    MAIL_REDIRECT_TO: str = ""
    MAIL_ALLOWLIST: str = ""
    
    UNSUBSCRIBE_SECRET: str = "change-me-in-production"
    TRACKING_SECRET: str = "change-me-in-production"
    BASE_URL: str = "http://localhost:5000"
    
    SCHEDULER_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    
    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = ["dev", "staging", "prod"]
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of: {allowed}")
        return v
    
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "prod"
    
    @property
    def mail_allowlist_domains(self) -> List[str]:
        if not self.MAIL_ALLOWLIST:
            return []
        return [d.strip() for d in self.MAIL_ALLOWLIST.split(",") if d.strip()]
    
    def validate_required_for_email(self) -> None:
        errors = []
        if not self.SENDGRID_API_KEY:
            errors.append("SENDGRID_API_KEY is required for sending emails")
        if not self.MAIL_FROM:
            errors.append("MAIL_FROM is required")
        if not self.is_production and not self.MAIL_REDIRECT_TO:
            errors.append("MAIL_REDIRECT_TO is required in dev/staging environments")
        if errors:
            raise ValueError("; ".join(errors))
    
    def validate_secrets_for_production(self) -> None:
        if self.is_production:
            errors = []
            if self.TRACKING_SECRET == "change-me-in-production":
                errors.append("TRACKING_SECRET must be set to a secure value in production")
            if self.UNSUBSCRIBE_SECRET == "change-me-in-production":
                errors.append("UNSUBSCRIBE_SECRET must be set to a secure value in production")
            if errors:
                raise ValueError("; ".join(errors))
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def get_settings() -> Settings:
    return settings
