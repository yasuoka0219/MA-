"""Email sending service with abstract interface for loose coupling"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.ma_tool.config import settings


@dataclass
class EmailMessage:
    to_email: str
    subject: str
    html_content: str
    from_email: Optional[str] = None


@dataclass
class EmailResult:
    success: bool
    status: str
    original_recipient: str
    actual_recipient: str
    message: Optional[str] = None


class EmailProvider(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> EmailResult:
        pass


class SendGridProvider(EmailProvider):
    def __init__(self, api_key: str, default_from: str):
        self.api_key = api_key
        self.default_from = default_from
    
    def send(self, message: EmailMessage) -> EmailResult:
        try:
            mail = Mail(
                from_email=message.from_email or self.default_from,
                to_emails=message.to_email,
                subject=message.subject,
                html_content=message.html_content
            )
            
            sg = SendGridAPIClient(self.api_key)
            response = sg.send(mail)
            
            return EmailResult(
                success=True,
                status="sent",
                original_recipient=message.to_email,
                actual_recipient=message.to_email,
                message=f"SendGrid response: {response.status_code}"
            )
        except Exception as e:
            return EmailResult(
                success=False,
                status="failed",
                original_recipient=message.to_email,
                actual_recipient=message.to_email,
                message=str(e)
            )


class MockEmailProvider(EmailProvider):
    def __init__(self):
        self.sent_messages: list[EmailMessage] = []
    
    def send(self, message: EmailMessage) -> EmailResult:
        self.sent_messages.append(message)
        return EmailResult(
            success=True,
            status="mock_sent",
            original_recipient=message.to_email,
            actual_recipient=message.to_email,
            message="Email logged (mock provider)"
        )


class EmailService:
    def __init__(self, provider: EmailProvider):
        self._provider = provider
        self._is_production = settings.is_production
        self._redirect_to = settings.MAIL_REDIRECT_TO
        self._allowlist_domains = settings.mail_allowlist_domains
    
    def _is_allowed_domain(self, email: str) -> bool:
        if not self._allowlist_domains:
            return True
        domain = email.split("@")[-1].lower()
        return any(domain.endswith(allowed.lower()) for allowed in self._allowlist_domains)
    
    def _apply_safety_guards(self, message: EmailMessage) -> tuple[EmailMessage, EmailResult | None]:
        original_recipient = message.to_email
        
        if self._is_production:
            return message, None
        
        if not self._is_allowed_domain(message.to_email) and not self._redirect_to:
            return message, EmailResult(
                success=False,
                status="blocked",
                original_recipient=original_recipient,
                actual_recipient="",
                message="Email blocked: domain not in allowlist and no redirect configured"
            )
        
        if not self._redirect_to:
            return message, EmailResult(
                success=False,
                status="blocked",
                original_recipient=original_recipient,
                actual_recipient="",
                message="No redirect configured for non-production environment"
            )
        
        redirected_message = EmailMessage(
            to_email=self._redirect_to,
            subject=f"[REDIRECTED from {original_recipient}] {message.subject}",
            html_content=message.html_content,
            from_email=message.from_email
        )
        
        return redirected_message, None
    
    def send(self, message: EmailMessage) -> EmailResult:
        original_recipient = message.to_email
        
        safe_message, blocked_result = self._apply_safety_guards(message)
        if blocked_result:
            return blocked_result
        
        result = self._provider.send(safe_message)
        
        if safe_message.to_email != original_recipient:
            result.original_recipient = original_recipient
            result.actual_recipient = safe_message.to_email
        
        return result


def get_email_service() -> EmailService:
    if settings.SENDGRID_API_KEY:
        provider = SendGridProvider(
            api_key=settings.SENDGRID_API_KEY,
            default_from=settings.MAIL_FROM
        )
    else:
        provider = MockEmailProvider()
    
    return EmailService(provider)


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    from_email: Optional[str] = None
) -> EmailResult:
    service = get_email_service()
    message = EmailMessage(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        from_email=from_email
    )
    return service.send(message)
