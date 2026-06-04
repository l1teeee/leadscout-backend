import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app.schemas.auth_schema import (
    ApproximateLocationRequest,
    AuthResponse,
    AuthUser,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OnboardingRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_AUTH_ERRORS: dict[str, str] = {
    "Invalid login credentials": "Email o contrasena incorrectos.",
    "Email not confirmed": "Confirma tu email antes de ingresar.",
    "User already registered": "Este correo ya tiene una cuenta.",
    "Password should be at least 6 characters": "La contrasena debe tener al menos 8 caracteres.",
}


def _friendly(exc: Exception) -> str:
    return _AUTH_ERRORS.get(str(exc), "Ocurrio un error. Intenta de nuevo.")


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    try:
        return await auth_service.login(body.email, body.password)
    except Exception as exc:
        logger.warning("Login failed for %s: %s", body.email, exc)
        raise HTTPException(status_code=401, detail=_friendly(exc))


@router.post("/register", status_code=201, response_model=MessageResponse)
async def register(body: RegisterRequest):
    try:
        await auth_service.register(body.email, body.password, body.full_name)
        return MessageResponse(message="Cuenta creada. Revisa tu email para confirmar.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly(exc))


@router.post("/logout", response_model=MessageResponse)
async def logout(authorization: Optional[str] = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    await auth_service.logout(token)
    return MessageResponse(message="Sesion cerrada.")


@router.get("/me", response_model=AuthUser)
async def me(authorization: Optional[str] = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    user = await auth_service.get_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token invalido o expirado.")
    return user


@router.put("/me/location", response_model=AuthUser)
async def update_location(body: ApproximateLocationRequest, authorization: Optional[str] = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        return await auth_service.update_approximate_location(
            token=token,
            latitude=body.latitude,
            longitude=body.longitude,
            label=body.label,
        )
    except Exception as exc:
        logger.error("Location update error: %s", exc)
        raise HTTPException(status_code=400, detail="No se pudo guardar la ubicacion aproximada.")


@router.post("/onboarding", response_model=AuthUser)
async def complete_onboarding(body: OnboardingRequest, authorization: Optional[str] = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        return await auth_service.complete_onboarding(token, body.model_dump(exclude_none=True))
    except Exception as exc:
        logger.error("Onboarding error: %s", exc)
        raise HTTPException(status_code=400, detail="No se pudo guardar la configuracion.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    # Always return success to avoid email enumeration
    redirect_url = f"{request.base_url}reset-password"
    try:
        await auth_service.forgot_password(body.email, redirect_url)
    except Exception as exc:
        logger.error("Forgot password error for %s: %s", body.email, exc)
    return MessageResponse(
        message="Si el correo existe, recibiras instrucciones para recuperar tu cuenta."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest):
    try:
        await auth_service.reset_password(body.access_token, body.new_password)
        return MessageResponse(message="Contrasena actualizada correctamente.")
    except Exception as exc:
        logger.error("Reset password error: %s", exc)
        raise HTTPException(status_code=400, detail="Token invalido o expirado.")
