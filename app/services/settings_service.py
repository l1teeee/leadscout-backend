import logging
from datetime import datetime, timezone

from app.async_utils import run_sync
from app.exceptions import ProfileUpdateError, SupportRequestError, WorkspaceNotFoundError
from app.repositories import (
    ai_usage_repository,
    search_audit_repository,
    workspaces_repository,
)
from app.schemas.auth_schema import AuthUser
from app.schemas.settings_schema import (
    AiContextSettings,
    AiContextUpdate,
    AuditEntry,
    AuditSettings,
    PublicSupportContactRequest,
    SupportContactRequest,
    TeamSettings,
    UsageSettings,
    UserProfileUpdate,
    WorkspaceUpdate,
)
from app.services import email_service

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


async def get_ai_context(workspace_id: str) -> AiContextSettings:
    workspace = await run_sync(workspaces_repository.get_workspace, workspace_id)
    row = workspace or {}
    return AiContextSettings(
        business_context=row.get("ai_business_context") or "",
        constraints=row.get("ai_constraints") or "",
        updated_at=str(row["ai_context_updated_at"]) if row.get("ai_context_updated_at") else None,
    )


async def update_ai_context(workspace_id: str, data: AiContextUpdate) -> AiContextSettings:
    payload: dict = {"ai_context_updated_at": datetime.now(timezone.utc).isoformat()}
    if data.business_context is not None:
        payload["ai_business_context"] = data.business_context
    if data.constraints is not None:
        payload["ai_constraints"] = data.constraints
    workspace = await run_sync(workspaces_repository.update_workspace, workspace_id, payload)
    row = workspace or {}
    return AiContextSettings(
        business_context=row.get("ai_business_context") or "",
        constraints=row.get("ai_constraints") or "",
        updated_at=str(row["ai_context_updated_at"]) if row.get("ai_context_updated_at") else None,
    )


async def send_support_request(user: AuthUser, data: SupportContactRequest) -> None:
    try:
        await email_service.send_support_email(
            from_email=user.email,
            from_name=user.full_name,
            workspace_name=user.workspace_name,
            subject=data.subject,
            message=data.message,
        )
        await email_service.send_support_confirmation_email(
            to_email=user.email,
            to_name=user.full_name,
            subject=data.subject,
        )
    except Exception as exc:
        logger.error("Support email error: %s", exc)
        raise SupportRequestError("No se pudo enviar la consulta.") from exc


async def send_public_support_request(data: PublicSupportContactRequest) -> None:
    try:
        await email_service.send_support_email(
            from_email=data.email,
            from_name=data.name,
            workspace_name=None,
            subject=data.subject,
            message=data.message,
        )
        await email_service.send_support_confirmation_email(
            to_email=data.email,
            to_name=data.name,
            subject=data.subject,
        )
    except Exception as exc:
        logger.error("Public support email error: %s", exc)
        raise SupportRequestError("No se pudo enviar la consulta.") from exc


async def get_audit(workspace_id: str, limit: int = 10) -> AuditSettings:
    rows = await run_sync(search_audit_repository.list_recent, workspace_id, limit)
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
