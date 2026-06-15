from fastapi import APIRouter, HTTPException, Query

from app.dependencies import CurrentToken, CurrentUser, CurrentWorkspace
from app.exceptions import ProfileUpdateError, WorkspaceNotFoundError
from app.schemas.auth_schema import AuthUser
from app.schemas.settings_schema import (
    AiContextExampleRequest,
    AiContextExampleResponse,
    AiContextImportRequest,
    AiContextImportResponse,
    AiContextSettings,
    AiContextUpdate,
    AuditSettings,
    TeamSettings,
    UsageSettings,
    UserProfileUpdate,
    WorkspaceSettings,
    WorkspaceUpdate,
)
from app.services import ai_service, settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/workspace", response_model=WorkspaceSettings)
async def get_workspace(workspace_id: CurrentWorkspace):
    try:
        return await settings_service.get_workspace(workspace_id)
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace no encontrado.")


@router.patch("/workspace", response_model=WorkspaceSettings)
async def update_workspace(body: WorkspaceUpdate, workspace_id: CurrentWorkspace):
    if not body.model_dump(exclude_none=True):
        raise HTTPException(status_code=422, detail="No hay campos para actualizar.")
    try:
        return await settings_service.update_workspace(workspace_id, body)
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace no encontrado.")


@router.get("/profile", response_model=AuthUser)
async def get_profile(user: CurrentUser):
    return user


@router.patch("/profile", response_model=AuthUser)
async def update_profile(body: UserProfileUpdate, token: CurrentToken, _: CurrentUser):
    if not body.model_dump(exclude_none=True):
        raise HTTPException(status_code=422, detail="No hay campos para actualizar.")
    try:
        return await settings_service.update_profile(token, body)
    except ProfileUpdateError as exc:
        raise HTTPException(status_code=400, detail=exc.message)


@router.get("/team", response_model=TeamSettings)
async def get_team(workspace_id: CurrentWorkspace):
    return await settings_service.get_team(workspace_id)


@router.get("/usage", response_model=UsageSettings)
async def get_usage(workspace_id: CurrentWorkspace):
    return await settings_service.get_usage(workspace_id)


@router.get("/audit", response_model=AuditSettings)
async def get_audit(workspace_id: CurrentWorkspace, limit: int = Query(10, ge=1, le=100)):
    return await settings_service.get_audit(workspace_id, limit)


@router.get("/ai-context", response_model=AiContextSettings)
async def get_ai_context(workspace_id: CurrentWorkspace):
    return await settings_service.get_ai_context(workspace_id)


@router.patch("/ai-context", response_model=AiContextSettings)
async def update_ai_context(body: AiContextUpdate, workspace_id: CurrentWorkspace):
    if not body.model_dump(exclude_none=True):
        raise HTTPException(status_code=422, detail="No hay campos para actualizar.")
    return await settings_service.update_ai_context(workspace_id, body)


@router.post("/ai-context/example", response_model=AiContextExampleResponse)
async def generate_ai_context_example(body: AiContextExampleRequest, _: CurrentWorkspace):
    try:
        result = await ai_service.generate_ai_context_example(body.business_type, body.lang)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/ai-context/import", response_model=AiContextImportResponse)
async def import_ai_context(body: AiContextImportRequest, _: CurrentWorkspace):
    try:
        result = await ai_service.import_ai_context_from_json(body.json_payload, body.lang)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
