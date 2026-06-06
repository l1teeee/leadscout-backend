from fastapi import APIRouter, Request

from app.dependencies import CurrentUser, CurrentWorkspace
from app.rate_limit import limiter
from app.schemas.explorer_schema import ExplorerSearchRequest, ExplorerSearchResponse
from app.services import explorer_service

router = APIRouter(prefix="/explorer", tags=["explorer"])


@router.post("/search", response_model=ExplorerSearchResponse)
@limiter.limit("30/minute")
async def search(request: Request, body: ExplorerSearchRequest, user: CurrentUser, workspace_id: CurrentWorkspace):
    return await explorer_service.search_and_save(workspace_id, user.id, body)
