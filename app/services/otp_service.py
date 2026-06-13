import random
import string
import logging

from app.cache import cache

logger = logging.getLogger(__name__)

TTL_OTP = 600  # 10 minutes


def _key(email: str, otp_type: str) -> str:
    return f"otp:{otp_type}:{email.lower()}"


async def generate_and_store(email: str, otp_type: str, user_id: str) -> str:
    """Generate a 6-digit OTP, store it in cache, return the code."""
    code = "".join(random.choices(string.digits, k=6))
    await cache.set(_key(email, otp_type), {"code": code, "user_id": user_id}, ttl=TTL_OTP)
    return code


async def verify(email: str, otp_type: str, code: str) -> str:
    """Verify OTP code. Returns user_id on success, raises ValueError on failure."""
    entry = await cache.get(_key(email, otp_type))
    if not entry:
        raise ValueError("Codigo expirado o no encontrado. Solicita uno nuevo.")
    if entry.get("code") != code.strip():
        raise ValueError("Codigo incorrecto.")
    await cache.delete(_key(email, otp_type))
    return str(entry["user_id"])
