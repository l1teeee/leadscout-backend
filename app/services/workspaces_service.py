import logging

from app.async_utils import run_sync
from app.exceptions import ExternalServiceError, WorkspaceAccessDeniedError
from app.repositories import workspace_members_repository
from app.schemas.workspace_schema import WorkspaceCreate, WorkspaceSummary
from app.services import auth_service

logger = logging.getLogger(__name__)


def _db_required():
    from app.services import supabase_service
    client = supabase_service.get_client()
    if not client:
        raise ExternalServiceError("Supabase", "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
    return client


async def list_workspaces(user_id: str, active_workspace_id: str | None) -> list[WorkspaceSummary]:
    rows = await run_sync(workspace_members_repository.list_for_user, user_id)
    return [
        WorkspaceSummary(
            id=row["workspace_id"],
            name=(row.get("workspaces") or {}).get("name", ""),
            role=row["role"],
            is_active=(row["workspace_id"] == active_workspace_id),
        )
        for row in rows
    ]


def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:60] or "workspace"


async def _activate_workspace(token: str, user_id: str, workspace_id: str, workspace_name: str) -> None:
    """Make workspace_id the caller's active workspace.

    Must write BOTH `profiles.workspace_id` and the Supabase Auth
    `user_metadata.workspace_id` — auth_service.login() resolves the
    active workspace from user_metadata first, falling back to the
    profiles row only if metadata is empty. Writing only the profiles
    row makes switching look like it worked for the current session,
    but a subsequent fresh login silently reverts the user back to
    their old workspace. complete_onboarding() already follows this
    same dual-write for the same reason.
    """
    client = _db_required()

    await run_sync(lambda: (
        client.table("profiles").update({"workspace_id": workspace_id}).eq("id", user_id).execute()
    ))

    try:
        admin_resp = await run_sync(lambda: client.auth.admin.get_user_by_id(user_id))
        existing_meta = admin_resp.user.user_metadata or {}
    except Exception:
        logger.warning("Could not read auth metadata while activating workspace for user %s", user_id, exc_info=True)
        existing_meta = {}

    updated_meta = {**existing_meta, "workspace_id": workspace_id, "workspace_name": workspace_name}
    try:
        await run_sync(lambda: client.auth.admin.update_user_by_id(user_id, {"user_metadata": updated_meta}))
    except Exception:
        logger.warning("Could not update auth metadata while activating workspace for user %s", user_id, exc_info=True)

    from app.cache import cache
    await cache.delete(auth_service._token_cache_key(token))


async def create_workspace(token: str, user_id: str, data: WorkspaceCreate) -> WorkspaceSummary:
    client = _db_required()

    workspace_payload: dict = {
        "name": data.name,
        "slug": f"{_slugify(data.name)}-{user_id[:8]}",
        "country": data.country or "El Salvador",
    }
    if data.industry:
        workspace_payload["industry"] = data.industry
    if data.city:
        workspace_payload["city"] = data.city

    ws_result = await run_sync(lambda: client.table("workspaces").insert(workspace_payload).execute())
    workspace_id = ws_result.data[0]["id"]

    await run_sync(workspace_members_repository.add_member, workspace_id, user_id, "owner")
    await _activate_workspace(token, user_id, workspace_id, data.name)

    return WorkspaceSummary(id=workspace_id, name=data.name, role="owner", is_active=True)


async def switch_workspace(token: str, user_id: str, workspace_id: str) -> WorkspaceSummary:
    is_member = await run_sync(workspace_members_repository.is_member, user_id, workspace_id)
    if not is_member:
        raise WorkspaceAccessDeniedError(workspace_id)

    client = _db_required()
    ws_result = await run_sync(lambda: (
        client.table("workspaces").select("name").eq("id", workspace_id).maybe_single().execute()
    ))
    workspace_name = (ws_result.data or {}).get("name", "") if ws_result else ""

    await _activate_workspace(token, user_id, workspace_id, workspace_name)

    rows = await run_sync(workspace_members_repository.list_for_user, user_id)
    role = next((r["role"] for r in rows if r["workspace_id"] == workspace_id), "owner")
    return WorkspaceSummary(id=workspace_id, name=workspace_name, role=role, is_active=True)
