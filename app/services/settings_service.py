import logging

from app.async_utils import run_sync
from app.exceptions import ProfileUpdateError, WorkspaceNotFoundError
from app.repositories import leads_repository, workspaces_repository
from app.schemas.auth_schema import AuthUser
from app.schemas.settings_schema import TeamSettings, UsageSettings, UserProfileUpdate, WorkspaceUpdate

logger = logging.getLogger(__name__)


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
    leads_data = await run_sync(leads_repository.list_leads, workspace_id, limit=1, offset=0)
    return UsageSettings(
        leads_used=leads_data.get("total", 0),
        leads_limit=500,
        searches_used=0,
        searches_limit=100,
        api_calls_used=0,
        api_calls_limit=1000,
    )
