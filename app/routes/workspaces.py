from fastapi import APIRouter, Request

from app.dependencies import CurrentToken, CurrentUser
from app.rate_limit import limiter
from app.schemas.workspace_schema import WorkspaceCreate, WorkspaceSummary
from app.services import workspaces_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceSummary])
async def list_workspaces(user: CurrentUser):
    return await workspaces_service.list_workspaces(user.id, user.workspace_id)


@router.post("", response_model=WorkspaceSummary, status_code=201)
@limiter.limit("5/minute")
async def create_workspace(request: Request, body: WorkspaceCreate, token: CurrentToken, user: CurrentUser):
    return await workspaces_service.create_workspace(token, user.id, body)


@router.post("/{workspace_id}/switch", response_model=WorkspaceSummary)
@limiter.limit("20/minute")
async def switch_workspace(request: Request, workspace_id: str, token: CurrentToken, user: CurrentUser):
    return await workspaces_service.switch_workspace(token, user.id, workspace_id)
