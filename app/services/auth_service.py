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


def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:60] or "workspace"


async def complete_onboarding(token: str, data: dict) -> AuthUser:
    client = _db()
    if not client:
        logger.info("Mock auth: complete onboarding")
        return AuthUser(id="mock-user-id", email="demo@example.com", full_name=data.get("full_name"), onboarded=True)

    user_response = client.auth.get_user(token)
    user_id = str(user_response.user.id)
    email = user_response.user.email or ""

    workspace_name = data.get("workspace_name") or "Mi Workspace"
    slug = f"{_slugify(workspace_name)}-{user_id[:4]}"

    # Create workspace row
    workspace_payload: dict = {
        "name": workspace_name,
        "slug": slug,
        "country": data.get("country", "El Salvador"),
    }
    for field in ("industry", "city", "phone", "website"):
        if data.get(field):
            workspace_payload[field] = data[field]

    ws_result = (
        client.table("workspaces")
        .insert(workspace_payload)
        .execute()
    )
    workspace_id: str = ws_result.data[0]["id"]

    # Create profile row (id == auth user id)
    client.table("profiles").insert({
        "id": user_id,
        "workspace_id": workspace_id,
        "email": email,
        "full_name": data.get("full_name"),
        "role": "owner",
    }).execute()

    # Store minimal flag + workspace_id in user_metadata for fast auth checks
    existing_meta = user_response.user.user_metadata or {}
    updated_meta = {
        **existing_meta,
        "onboarded": True,
        "workspace_id": workspace_id,
        "full_name": data.get("full_name"),
        "industry": data.get("industry"),
        "city": data.get("city"),
    }
    client.auth.admin.update_user_by_id(user_id, {"user_metadata": updated_meta})

    await cache.delete(_token_cache_key(token))

    return _user_from_meta(user_id, email, updated_meta)


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
