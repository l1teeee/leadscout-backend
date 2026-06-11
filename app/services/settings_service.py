import logging

from app.async_utils import run_sync
from app.exceptions import ProfileUpdateError, WorkspaceNotFoundError
from app.repositories import (
    ai_usage_repository,
    search_audit_repository,
    workspaces_repository,
)
from app.schemas.auth_schema import AuthUser
from app.schemas.settings_schema import (
    AuditEntry,
    AuditSettings,
    TeamSettings,
    UsageSettings,
    UserProfileUpdate,
    WorkspaceUpdate,
)

logger = logging.getLogger(__name__)

DEFAULT_PLAN = "starter"
PLAN_LIMITS: dict[str, dict[str, int]] = {
    "starter": {"searches": 100, "tokens": 200_000},
    "growth": {"searches": 500, "tokens": 1_000_000},
    "agency": {"searches": 2000, "tokens": 5_000_000},
}


async def get_workspace(workspace_id: str) -> dict:
    workspace = await run_sync(workspaces_repository.get_workspace, workspace_id)
    if not workspace:
        raise WorkspaceNotFoundError(workspace_id)
    return workspace


async def update_workspace(workspace_id: str, data: WorkspaceUpdate) -> dict:
    payload = data.model_dump(exclude_none=True)
    workspace = await run_sync(workspaces_repository.update_workspace, workspace_id, payload)
    if not workspace:
        raise WorkspaceNotFoundError(workspace_id)
    return workspace


async def update_profile(token: str, data: UserProfileUpdate) -> AuthUser:
    from app.services import auth_service
    payload = data.model_dump(exclude_none=True)
    try:
        return await auth_service.update_profile(token, payload)
    except Exception as exc:
        logger.error("Profile update error: %s", exc)
        raise ProfileUpdateError("No se pudo actualizar el perfil.") from exc


async def get_team(workspace_id: str) -> TeamSettings:
    members = await run_sync(workspaces_repository.get_team_members, workspace_id)
    return TeamSettings(members=members)


async def get_usage(workspace_id: str) -> UsageSettings:
    workspace = await run_sync(workspaces_repository.get_workspace, workspace_id)
    plan = (workspace or {}).get("plan") or DEFAULT_PLAN
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])
    searches_used = await run_sync(search_audit_repository.count_searches_this_month, workspace_id)
    tokens_used = await run_sync(ai_usage_repository.count_tokens_this_month, workspace_id)
    return UsageSettings(
        plan=plan,
        searches_used=searches_used,
        searches_limit=limits["searches"],
        tokens_used=tokens_used,
        tokens_limit=limits["tokens"],
    )


async def get_audit(workspace_id: str) -> AuditSettings:
    rows = await run_sync(search_audit_repository.list_recent, workspace_id, 10)
    entries = [
        AuditEntry(
            query=row.get("query"),
            location=row.get("location"),
            category=row.get("category"),
            results_count=row.get("results_count") or 0,
            created_at=str(row["created_at"]) if row.get("created_at") else None,
        )
        for row in rows
    ]
    return AuditSettings(entries=entries)
