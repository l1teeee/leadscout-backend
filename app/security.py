import uuid
from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

ACCESS_TOKEN_EXPIRE_DAYS = 7
_ALGORITHM = "HS256"
_DEV_FALLBACK_SECRET = "dev-only-insecure-secret-change-in-prod"


def _secret() -> str:
    from app.config import settings
    s = settings.SIGNING_SECRET.get_secret_value()
    return s or _DEV_FALLBACK_SECRET


def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except (ExpiredSignatureError, InvalidTokenError):
        return None
