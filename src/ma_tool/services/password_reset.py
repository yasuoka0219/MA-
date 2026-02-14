"""パスワードリセット用トークンの生成・検証"""
from typing import Optional

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from src.ma_tool.config import settings


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        settings.PASSWORD_RESET_SECRET,
        salt="password-reset",
    )


def generate_password_reset_token(user_id: int) -> str:
    """有効期限付きトークンを生成（PASSWORD_RESET_EXPIRE_SECONDS 秒）"""
    s = _get_serializer()
    return s.dumps({"user_id": user_id})


def verify_password_reset_token(token: str) -> Optional[int]:
    """トークンを検証し、有効なら user_id を返す。無効・期限切れなら None"""
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=settings.PASSWORD_RESET_EXPIRE_SECONDS)
        return data.get("user_id")
    except (BadSignature, SignatureExpired, TypeError):
        return None
