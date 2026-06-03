from fastapi import APIRouter

from app.schemas.explorer_schema import ExplorerSearchRequest, ExplorerSearchResponse
from app.services import explorer_service

router = APIRouter(prefix="/explorer", tags=["explorer"])

_WORKSPACE = "mock-workspace-id"


@router.post("/search", response_model=ExplorerSearchResponse)
async def search(body: ExplorerSearchRequest):
    return await explorer_service.search_and_save(_WORKSPACE, body)
