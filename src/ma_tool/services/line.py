"""LINE Messaging service with safety guards for dev/staging environments"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any
import logging

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from src.ma_tool.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LineMessage:
    to_user_id: str
    text: Optional[str] = None
    flex_message: Optional[dict] = None
    alt_text: str = "メッセージを受信しました"


@dataclass
class LineResult:
    success: bool
    status: str
    original_recipient: str
    actual_recipient: str
    provider_message_id: Optional[str] = None
    message: Optional[str] = None


class LineProvider(ABC):
    @abstractmethod
    def send(self, message: LineMessage) -> LineResult:
        pass


class LineBotProvider(LineProvider):
    def __init__(self, channel_access_token: str):
        self.channel_access_token = channel_access_token
        self._configuration = Configuration(access_token=channel_access_token)
    
    def send(self, message: LineMessage) -> LineResult:
        try:
            with ApiClient(self._configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                
                messages = []
                if message.text:
                    messages.append(TextMessage(text=message.text))  # type: ignore[call-arg]
                if message.flex_message:
                    flex_container = FlexContainer.from_dict(message.flex_message)
                    messages.append(FlexMessage(
                        altText=message.alt_text,
                        contents=flex_container
                    ))  # type: ignore[call-arg]
                
                if not messages:
                    return LineResult(
                        success=False,
                        status="failed",
                        original_recipient=message.to_user_id,
                        actual_recipient=message.to_user_id,
                        message="No message content provided"
                    )
                
                request = PushMessageRequest(
                    to=message.to_user_id,
                    messages=messages
                )  # type: ignore[call-arg]
                
                response = messaging_api.push_message_with_http_info(request)
                
                return LineResult(
                    success=True,
                    status="sent",
                    original_recipient=message.to_user_id,
                    actual_recipient=message.to_user_id,
                    provider_message_id=getattr(response, 'request_id', None),
                    message="LINE message sent successfully"
                )
        except Exception as e:
            logger.exception("Failed to send LINE message")
            return LineResult(
                success=False,
                status="failed",
                original_recipient=message.to_user_id,
                actual_recipient=message.to_user_id,
                message=str(e)
            )


class MockLineProvider(LineProvider):
    def __init__(self):
        self.sent_messages: list[LineMessage] = []
    
    def send(self, message: LineMessage) -> LineResult:
        self.sent_messages.append(message)
        return LineResult(
            success=True,
            status="mock_sent",
            original_recipient=message.to_user_id,
            actual_recipient=message.to_user_id,
            provider_message_id="mock_message_id",
            message="LINE message logged (mock provider)"
        )


class LineService:
    def __init__(self, provider: LineProvider):
        self._provider = provider
        self._is_production = settings.is_production
        self._test_user_id = settings.LINE_TEST_USER_ID
    
    def _apply_safety_guards(self, message: LineMessage) -> tuple[LineMessage, LineResult | None]:
        original_recipient = message.to_user_id
        
        if self._is_production:
            return message, None
        
        if not self._test_user_id:
            return message, LineResult(
                success=False,
                status="blocked",
                original_recipient=original_recipient,
                actual_recipient="",
                message="LINE message blocked: LINE_TEST_USER_ID not configured for dev/staging"
            )
        
        redirected_text = None
        if message.text:
            redirected_text = f"[REDIRECTED from {original_recipient}]\n{message.text}"
        
        redirected_alt_text = f"[REDIRECTED from {original_recipient}] {message.alt_text}"
        
        redirected_message = LineMessage(
            to_user_id=self._test_user_id,
            text=redirected_text,
            flex_message=message.flex_message,
            alt_text=redirected_alt_text
        )
        
        return redirected_message, None
    
    def send(self, message: LineMessage) -> LineResult:
        original_recipient = message.to_user_id
        
        safe_message, blocked_result = self._apply_safety_guards(message)
        if blocked_result:
            return blocked_result
        
        result = self._provider.send(safe_message)
        
        if safe_message.to_user_id != original_recipient:
            result.original_recipient = original_recipient
            result.actual_recipient = safe_message.to_user_id
        
        return result


def get_line_service() -> LineService:
    if settings.LINE_CHANNEL_ACCESS_TOKEN:
        provider = LineBotProvider(
            channel_access_token=settings.LINE_CHANNEL_ACCESS_TOKEN
        )
    else:
        provider = MockLineProvider()
    
    return LineService(provider)


def send_line_message(
    to_user_id: str,
    text: Optional[str] = None,
    flex_message: Optional[dict] = None,
    alt_text: str = "メッセージを受信しました"
) -> LineResult:
    service = get_line_service()
    message = LineMessage(
        to_user_id=to_user_id,
        text=text,
        flex_message=flex_message,
        alt_text=alt_text
    )
    return service.send(message)
