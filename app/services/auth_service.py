import logging
from datetime import UTC, datetime

from app.async_utils import run_sync
from app.cache import TTL_AUTH_TOKEN, cache
from app.exceptions import ExternalServiceError
from app.schemas.auth_schema import AuthResponse, AuthUser

logger = logging.getLogger(__name__)


def _db():
    from app.services import supabase_service
    return supabase_service.get_client()


def _db_required():
    client = _db()
    if not client:
        raise ExternalServiceError("Supabase", "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
    return client


def _token_cache_key(token: str) -> str:
    import hashlib
    return f"auth:user:{hashlib.sha256(token.encode()).hexdigest()[:32]}"


async def _profile_for_user(client, user_id: str) -> dict:
    try:
        result = await run_sync(lambda: (
            client.table("profiles")
            .select(
                "workspace_id, full_name, role, approximate_latitude, "
                "approximate_longitude, approximate_location_label"
            )
            .eq("id", user_id)
            .maybe_single()
            .execute()
        ))
        return result.data or {} if result else {}
    except Exception:
        logger.exception("Could not resolve profile for user %s", user_id)
        return {}


async def _workspace_for_id(client, workspace_id: str | None) -> dict:
    if not workspace_id:
        return {}
    try:
        result = await run_sync(lambda: (
            client.table("workspaces")
            .select("name, industry, country, city")
            .eq("id", workspace_id)
            .maybe_single()
            .execute()
        ))
        if result is None:
            return {}
        return result.data or {}
    except Exception:
        logger.exception("Could not resolve workspace %s", workspace_id)
        return {}


def _user_from_meta(user_id: str, email: str, meta: dict) -> AuthUser:
    return AuthUser(
        id=user_id,
        email=email,
        full_name=meta.get("full_name"),
        role=meta.get("role", "owner"),
        onboarded=bool(meta.get("onboarded", False)),
        workspace_id=meta.get("workspace_id"),
        workspace_name=meta.get("workspace_name"),
        industry=meta.get("industry"),
        country=meta.get("country"),
        city=meta.get("city"),
        approximate_latitude=meta.get("approximate_latitude"),
        approximate_longitude=meta.get("approximate_longitude"),
        approximate_location_label=meta.get("approximate_location_label"),
    )


def _user_from_sources(user_id: str, email: str, meta: dict, profile: dict, workspace: dict) -> AuthUser:
    workspace_id = meta.get("workspace_id") or profile.get("workspace_id")
    return AuthUser(
        id=user_id,
        email=email,
        full_name=meta.get("full_name") or profile.get("full_name"),
        role=meta.get("role") or profile.get("role") or "owner",
        onboarded=bool(meta.get("onboarded") or workspace_id),
        workspace_id=workspace_id,
        workspace_name=meta.get("workspace_name") or workspace.get("name"),
        industry=meta.get("industry") or workspace.get("industry"),
        country=meta.get("country") or workspace.get("country"),
        city=meta.get("city") or workspace.get("city"),
        approximate_latitude=profile.get("approximate_latitude") or meta.get("approximate_latitude"),
        approximate_longitude=profile.get("approximate_longitude") or meta.get("approximate_longitude"),
        approximate_location_label=profile.get("approximate_location_label") or meta.get("approximate_location_label"),
    )


def _round_approx(value: float) -> float:
    return round(value, 2)


def _sign(user: AuthUser) -> AuthUser:
    """Attach a fresh HMAC signature. Called after cache.set so cached data stays unsigned."""
    from app.services import signing_service
    sig = signing_service.generate_user_signature(user.id, user.workspace_id)
    if sig:
        return user.model_copy(update={"user_signature": sig})
    return user


async def login(email: str, password: str) -> AuthResponse:
    client = _db_required()

    response = await run_sync(lambda: client.auth.sign_in_with_password({"email": email, "password": password}))
    meta = response.user.user_metadata or {}
    user_id = str(response.user.id)
    profile = await _profile_for_user(client, user_id)
    workspace = await _workspace_for_id(client, meta.get("workspace_id") or profile.get("workspace_id"))
    user = _user_from_sources(user_id, response.user.email or email, meta, profile, workspace)
    await cache.set(_token_cache_key(response.session.access_token), user.model_dump(), ttl=TTL_AUTH_TOKEN)
    return AuthResponse(access_token=response.session.access_token, user=_sign(user))


async def register(email: str, password: str, full_name: str | None = None) -> None:
    client = _db_required()

    options: dict = {}
    if full_name:
        options["data"] = {"full_name": full_name}

    await run_sync(lambda: client.auth.sign_up({"email": email, "password": password, "options": options}))


async def logout(token: str) -> None:
    await cache.delete(_token_cache_key(token))
    client = _db()
    if not client:
        return
    try:
        await run_sync(lambda: client.auth.admin.sign_out(token))
    except Exception:
        pass  # Best-effort: token may already be expired


async def get_user(token: str) -> AuthUser | None:
    key = _token_cache_key(token)
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: auth token")
        return _sign(AuthUser(**cached))

    client = _db()
    if not client:
        return None

    try:
        response = await run_sync(lambda: client.auth.get_user(token))
        meta = response.user.user_metadata or {}
        user_id = str(response.user.id)
        profile = await _profile_for_user(client, user_id)
        workspace = await _workspace_for_id(client, meta.get("workspace_id") or profile.get("workspace_id"))
        user = _user_from_sources(user_id, response.user.email or "", meta, profile, workspace)
        await cache.set(key, user.model_dump(), ttl=TTL_AUTH_TOKEN)
        return _sign(user)
    except Exception:
        return None


async def forgot_password(email: str, redirect_url: str) -> None:
    client = _db_required()
    await run_sync(lambda: client.auth.reset_password_for_email(email, {"redirect_to": redirect_url}))


def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:60] or "workspace"


async def complete_onboarding(token: str, data: dict) -> AuthUser:
    client = _db_required()

    user_response = await run_sync(lambda: client.auth.get_user(token))
    user_id = str(user_response.user.id)
    email = user_response.user.email or ""
    existing_meta = user_response.user.user_metadata or {}
    existing_profile = await _profile_for_user(client, user_id)

    workspace_name = data.get("workspace_name") or "Mi Workspace"
    slug = f"{_slugify(workspace_name)}-{user_id[:8]}"

    workspace_payload: dict = {
        "name": workspace_name,
        "slug": slug,
        "country": data.get("country", "El Salvador"),
    }
    for field in ("industry", "city", "phone", "website"):
        if data.get(field):
            workspace_payload[field] = data[field]

    workspace_id = existing_meta.get("workspace_id") or existing_profile.get("workspace_id")
    if workspace_id:
        await run_sync(lambda: client.table("workspaces").update(workspace_payload).eq("id", workspace_id).execute())
    else:
        try:
            ws_result = await run_sync(lambda: client.table("workspaces").insert(workspace_payload).execute())
            workspace_id = ws_result.data[0]["id"]
        except Exception:
            # If a previous attempt created the workspace but failed before profile insert,
            # recover it by slug instead of crashing on the unique constraint.
            ws_result = await run_sync(lambda: (
                client.table("workspaces")
                .select("id")
                .eq("slug", slug)
                .maybe_single()
                .execute()
            ))
            if ws_result is None or not ws_result.data:
                raise
            workspace_id = ws_result.data["id"]

    profile_payload = {
        "id": user_id,
        "workspace_id": workspace_id,
        "email": email,
        "full_name": data.get("full_name"),
        "role": "owner",
    }
    await run_sync(lambda: client.table("profiles").upsert(profile_payload, on_conflict="id").execute())

    updated_meta = {
        **existing_meta,
        "onboarded": True,
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "full_name": data.get("full_name"),
        "role": "owner",
        "industry": data.get("industry"),
        "country": data.get("country"),
        "city": data.get("city"),
    }
    await run_sync(lambda: client.auth.admin.update_user_by_id(user_id, {"user_metadata": updated_meta}))

    await cache.delete(_token_cache_key(token))

    return _sign(_user_from_meta(user_id, email, updated_meta))


async def update_approximate_location(token: str, latitude: float, longitude: float, label: str | None) -> AuthUser:
    client = _db_required()

    user_response = await run_sync(lambda: client.auth.get_user(token))
    user_id = str(user_response.user.id)
    email = user_response.user.email or ""
    meta = user_response.user.user_metadata or {}
    profile = await _profile_for_user(client, user_id)
    workspace = await _workspace_for_id(client, meta.get("workspace_id") or profile.get("workspace_id"))

    rounded_lat = _round_approx(latitude)
    rounded_lng = _round_approx(longitude)
    location_meta = {
        "approximate_latitude": rounded_lat,
        "approximate_longitude": rounded_lng,
        "approximate_location_label": label,
    }

    try:
        await run_sync(lambda: client.table("profiles").update({
            **location_meta,
            "location_updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", user_id).execute())
        profile = {**profile, **location_meta}
    except Exception:
        logger.exception("Could not persist approximate location in profiles for user %s", user_id)

    try:
        await run_sync(lambda: client.auth.admin.update_user_by_id(user_id, {"user_metadata": {**meta, **location_meta}}))
    except Exception:
        logger.exception("Could not persist approximate location metadata for user %s", user_id)

    await cache.delete(_token_cache_key(token))
    return _sign(_user_from_sources(user_id, email, {**meta, **location_meta}, profile, workspace))


async def update_profile(token: str, data: dict) -> AuthUser:
    client = _db_required()

    user_response = await run_sync(lambda: client.auth.get_user(token))
    user_id = str(user_response.user.id)
    email = user_response.user.email or ""
    meta = user_response.user.user_metadata or {}

    profile_update = {k: v for k, v in data.items() if k in ("full_name", "role")}
    if profile_update:
        try:
            await run_sync(lambda: client.table("profiles").update(profile_update).eq("id", user_id).execute())
        except Exception:
            logger.exception("Could not update profile for user %s", user_id)

    updated_meta = {**meta, **{k: v for k, v in data.items() if k in ("full_name", "role")}}
    if updated_meta != meta:
        try:
            await run_sync(lambda: client.auth.admin.update_user_by_id(user_id, {"user_metadata": updated_meta}))
        except Exception:
            logger.exception("Could not update user_metadata for user %s", user_id)

    await cache.delete(_token_cache_key(token))
    profile = await _profile_for_user(client, user_id)
    workspace = await _workspace_for_id(client, updated_meta.get("workspace_id") or profile.get("workspace_id"))
    return _sign(_user_from_sources(user_id, email, updated_meta, profile, workspace))


async def reset_password(access_token: str, new_password: str) -> None:
    await cache.delete(_token_cache_key(access_token))
    client = _db_required()

    user_response = await run_sync(lambda: client.auth.get_user(access_token))
    await run_sync(lambda: client.auth.admin.update_user_by_id(
        str(user_response.user.id),
        {"password": new_password},
    ))
