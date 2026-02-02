"""Password hashing and verification utilities"""
import bcrypt


def hash_password(password: str) -> str:
    """パスワードをハッシュ化して返す"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """パスワードが正しいか検証する"""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False
