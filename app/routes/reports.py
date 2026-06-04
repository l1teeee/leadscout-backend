from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.services import auth_service, reports_service

router = APIRouter(prefix="/reports", tags=["reports"])


async def _get_workspace(authorization: Optional[str]) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    user = await auth_service.get_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token invalido o expirado.")
    if not user.workspace_id:
        raise HTTPException(status_code=403, detail="Completa el onboarding para crear tu workspace.")
    return user.workspace_id


@router.get("/summary")
async def get_summary(authorization: Optional[str] = Header(None)):
    workspace_id = await _get_workspace(authorization)
    return await reports_service.get_summary(workspace_id)
