from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.schemas.explorer_schema import ExplorerSearchRequest, ExplorerSearchResponse
from app.services import auth_service, explorer_service

router = APIRouter(prefix="/explorer", tags=["explorer"])


async def _get_workspace(authorization: Optional[str]) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    user = await auth_service.get_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    if not user.workspace_id:
        raise HTTPException(status_code=403, detail="Completa el onboarding para crear tu workspace.")
    return user.workspace_id


@router.post("/search", response_model=ExplorerSearchResponse)
async def search(body: ExplorerSearchRequest, authorization: Optional[str] = Header(None)):
    workspace_id = await _get_workspace(authorization)
    return await explorer_service.search_and_save(workspace_id, body)
