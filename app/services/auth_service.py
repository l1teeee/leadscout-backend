import logging
from typing import Optional

from app.cache import TTL_AUTH_TOKEN, cache
from app.schemas.auth_schema import AuthResponse, AuthUser

logger = logging.getLogger(__name__)

_MOCK_PREFIX = "mock::"


def _mock_token(email: str) -> str:
    return f"{_MOCK_PREFIX}{email}"


def _is_mock(token: str) -> bool:
    return token.startswith(_MOCK_PREFIX)


def _user_from_mock(token: str) -> AuthUser:
    email = token[len(_MOCK_PREFIX):]
    return AuthUser(id="mock-user-id", email=email, full_name="Demo User", role="owner")


def _db():
    from app.services import supabase_service
    return supabase_service.get_client()


def _token_cache_key(token: str) -> str:
    # Use only the first 40 chars so we never store full tokens in cache keys
    return f"auth:user:{token[:40]}"


def _user_from_meta(user_id: str, email: str, meta: dict) -> AuthUser:
    return AuthUser(
        id=user_id,
        email=email,
        full_name=meta.get("full_name"),
        role=meta.get("role", "owner"),
        onboarded=bool(meta.get("onboarded", False)),
        workspace_name=meta.get("workspace_name"),
        industry=meta.get("industry"),
        city=meta.get("city"),
    )


async def login(email: str, password: str) -> AuthResponse:
    client = _db()
    if not client:
        logger.info("Mock auth: login %s", email)
        user = AuthUser(id="mock-user-id", email=email, full_name="Demo User", role="owner")
        return AuthResponse(access_token=_mock_token(email), user=user)

    response = client.auth.sign_in_with_password({"email": email, "password": password})
    meta = response.user.user_metadata or {}
    user = _user_from_meta(str(response.user.id), response.user.email or email, meta)
    await cache.set(_token_cache_key(response.session.access_token), user.model_dump(), ttl=TTL_AUTH_TOKEN)
    return AuthResponse(access_token=response.session.access_token, user=user)


async def register(email: str, password: str, full_name: Optional[str] = None) -> None:
    client = _db()
    if not client:
        logger.info("Mock auth: register %s", email)
        return

    options: dict = {}
    if full_name:
        options["data"] = {"full_name": full_name}

    client.auth.sign_up({"email": email, "password": password, "options": options})


async def logout(token: str) -> None:
    await cache.delete(_token_cache_key(token))
    if _is_mock(token):
        return
    client = _db()
    if not client:
        return
    try:
        client.auth.admin.sign_out(token)
    except Exception:
        pass  # Best-effort: token may already be expired


async def get_user(token: str) -> Optional[AuthUser]:
    if _is_mock(token):
        return _user_from_mock(token)

    key = _token_cache_key(token)
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: auth token")
        return AuthUser(**cached)

    client = _db()
    if not client:
        return None

    try:
        response = client.auth.get_user(token)
        meta = response.user.user_metadata or {}
        user = _user_from_meta(str(response.user.id), response.user.email or "", meta)
        await cache.set(key, user.model_dump(), ttl=TTL_AUTH_TOKEN)
        return user
    except Exception:
        return None


async def forgot_password(email: str, redirect_url: str) -> None:
    client = _db()
    if not client:
        logger.info("Mock auth: forgot password for %s", email)
        return
    client.auth.reset_password_for_email(email, {"redirect_to": redirect_url})


async def complete_onboarding(token: str, data: dict) -> AuthUser:
    client = _db()
    if not client:
        logger.info("Mock auth: complete onboarding")
        return AuthUser(id="mock-user-id", email="demo@example.com", full_name=data.get("full_name"), onboarded=True)

    # Merge incoming data into existing metadata (preserve fields not sent)
    user_response = client.auth.get_user(token)
    existing_meta = user_response.user.user_metadata or {}
    updated_meta = {**existing_meta, **data, "onboarded": True}

    client.auth.admin.update_user_by_id(
        str(user_response.user.id),
        {"user_metadata": updated_meta},
    )

    # Invalidate cache so next get_user reads fresh metadata
    await cache.delete(_token_cache_key(token))

    return _user_from_meta(
        str(user_response.user.id),
        user_response.user.email or "",
        updated_meta,
    )


async def reset_password(access_token: str, new_password: str) -> None:
    await cache.delete(_token_cache_key(access_token))
    client = _db()
    if not client:
        logger.info("Mock auth: reset password")
        return

    user_response = client.auth.get_user(access_token)
    client.auth.admin.update_user_by_id(
        str(user_response.user.id),
        {"password": new_password},
    )
