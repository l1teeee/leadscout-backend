from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Request

from app.schemas.auth_schema import AuthUser
from app.services import auth_service


async def get_current_token(authorization: Optional[str] = Header(None)) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    return token


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(get_current_token)],
) -> AuthUser:
    user = await auth_service.get_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token invalido o expirado.")
    request.state.user_id = user.id
    return user


async def get_current_workspace(user: Annotated[AuthUser, Depends(get_current_user)]) -> str:
    if not user.workspace_id:
        raise HTTPException(status_code=403, detail="Completa el onboarding para crear tu workspace.")
    return user.workspace_id


CurrentToken = Annotated[str, Depends(get_current_token)]
CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
CurrentWorkspace = Annotated[str, Depends(get_current_workspace)]
