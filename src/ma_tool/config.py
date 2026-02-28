"""Application settings using Pydantic Settings"""
from typing import Optional, List
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    
    SENDGRID_API_KEY: str = ""
    
    APP_ENV: str = "dev"
    
    MAIL_FROM: str = "noreply@example.com"
    MAIL_REPLY_TO: str = ""
    MAIL_REDIRECT_TO: str = ""
    MAIL_ALLOWLIST: str = ""
    
    LINE_FRIEND_ADD_URL: str = ""
    
    UNSUBSCRIBE_SECRET: str = "change-me-in-production"
    TRACKING_SECRET: str = "change-me-in-production"
    PASSWORD_RESET_SECRET: str = "change-me-in-production"
    PASSWORD_RESET_EXPIRE_SECONDS: int = 3600  # 1時間
    BASE_URL: str = "http://localhost:5000"
    
    SCHEDULER_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    
    LINE_CHANNEL_ACCESS_TOKEN: str = ""
    LINE_CHANNEL_SECRET: str = ""
    LINE_TEST_USER_ID: str = ""
    
    SESSION_SECRET_KEY: str = ""
    
    IMPORTANT_PAGE_PATHS: str = "/apply,/exam,/entry,/admission,/nyushi,/shutsugan,/opencampus"
    TRACKING_ALLOWED_ORIGINS: str = ""
    
    SCORE_OPEN: int = 1
    SCORE_CLICK: int = 3
    SCORE_PAGE_VIEW: int = 1
    SCORE_IMPORTANT_CLICK: int = 5
    SCORE_IMPORTANT_PAGE_VIEW: int = 3
    
    SCORE_BAND_WARM: int = 3
    SCORE_BAND_HOT: int = 8
    
    # CSVインポート: アップロード許容サイズ（MB）。本番で 413 やタイムアウトが出る場合は小さくする
    CSV_MAX_UPLOAD_MB: int = 50
    
    @property
    def important_page_list(self) -> List[str]:
        if not self.IMPORTANT_PAGE_PATHS:
            return []
        return [p.strip() for p in self.IMPORTANT_PAGE_PATHS.split(",") if p.strip()]
    
    @property
    def tracking_allowed_origins_list(self) -> List[str]:
        if not self.TRACKING_ALLOWED_ORIGINS:
            return []
        return [o.strip() for o in self.TRACKING_ALLOWED_ORIGINS.split(",") if o.strip()]
    
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
            if self.PASSWORD_RESET_SECRET == "change-me-in-production":
                errors.append("PASSWORD_RESET_SECRET must be set to a secure value in production")
            if errors:
                raise ValueError("; ".join(errors))
    
    def validate_required_for_line(self) -> None:
        errors = []
        if not self.LINE_CHANNEL_ACCESS_TOKEN:
            errors.append("LINE_CHANNEL_ACCESS_TOKEN is required for LINE messaging")
        if not self.LINE_CHANNEL_SECRET:
            errors.append("LINE_CHANNEL_SECRET is required for LINE messaging")
        if not self.is_production and not self.LINE_TEST_USER_ID:
            errors.append("LINE_TEST_USER_ID is required in dev/staging environments")
        if errors:
            raise ValueError("; ".join(errors))
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def get_settings() -> Settings:
    return settings
