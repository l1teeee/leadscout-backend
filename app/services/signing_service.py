import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional


def _day_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def generate_user_signature(user_id: str, workspace_id: Optional[str]) -> str:
    from app.config import settings
    if not settings.SIGNING_SECRET:
        return ""
    message = f"{user_id}:{workspace_id or ''}:{_day_stamp()}"
    return hmac.new(
        settings.SIGNING_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_user_signature(signature: str, user_id: str, workspace_id: Optional[str]) -> bool:
    expected = generate_user_signature(user_id, workspace_id)
    if not expected:
        return False
    return hmac.compare_digest(expected, signature)
