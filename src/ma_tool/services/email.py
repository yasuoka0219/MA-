"""Email sending service with safety guards"""
from typing import Optional, Tuple
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.ma_tool.config import settings


class EmailResult:
    def __init__(
        self,
        success: bool,
        status: str,
        original_recipient: str,
        actual_recipient: str,
        message: Optional[str] = None
    ):
        self.success = success
        self.status = status
        self.original_recipient = original_recipient
        self.actual_recipient = actual_recipient
        self.message = message


def is_allowed_domain(email: str) -> bool:
    if not settings.mail_allowlist_domains:
        return True
    domain = email.split("@")[-1].lower()
    return any(domain.endswith(allowed.lower()) for allowed in settings.mail_allowlist_domains)


def get_actual_recipient(original_email: str) -> Tuple[str, bool]:
    if settings.is_production:
        return original_email, True
    
    if settings.MAIL_REDIRECT_TO:
        return settings.MAIL_REDIRECT_TO, True
    
    return original_email, False


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    from_email: Optional[str] = None
) -> EmailResult:
    original_recipient = to_email
    
    if not settings.is_production and not is_allowed_domain(to_email):
        if not settings.MAIL_REDIRECT_TO:
            return EmailResult(
                success=False,
                status="blocked",
                original_recipient=original_recipient,
                actual_recipient="",
                message=f"Email blocked: domain not in allowlist and no redirect configured"
            )
    
    actual_recipient, should_send = get_actual_recipient(to_email)
    
    if not should_send:
        return EmailResult(
            success=False,
            status="blocked",
            original_recipient=original_recipient,
            actual_recipient="",
            message="No redirect configured for non-production environment"
        )
    
    if not settings.SENDGRID_API_KEY:
        return EmailResult(
            success=False,
            status="failed",
            original_recipient=original_recipient,
            actual_recipient=actual_recipient,
            message="SENDGRID_API_KEY not configured"
        )
    
    try:
        message = Mail(
            from_email=from_email or settings.MAIL_FROM,
            to_emails=actual_recipient,
            subject=subject,
            html_content=html_content
        )
        
        if not settings.is_production and original_recipient != actual_recipient:
            message.subject = f"[REDIRECTED from {original_recipient}] {subject}"
        
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        
        return EmailResult(
            success=True,
            status="sent",
            original_recipient=original_recipient,
            actual_recipient=actual_recipient,
            message=f"SendGrid response: {response.status_code}"
        )
    except Exception as e:
        return EmailResult(
            success=False,
            status="failed",
            original_recipient=original_recipient,
            actual_recipient=actual_recipient,
            message=str(e)
        )
