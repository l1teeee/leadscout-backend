import logging

from fastapi import APIRouter, Header, HTTPException, Request
from slowapi.util import get_remote_address

from app.dependencies import CurrentToken, CurrentUser
from app.exceptions import ExternalServiceError
from app.rate_limit import limiter
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
    VerifyRegistrationOtpRequest,
    VerifyResetOtpRequest,
    ResetPasswordOtpRequest,
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
@limiter.limit("5/minute", key_func=get_remote_address)
async def login(request: Request, body: LoginRequest):
    try:
        return await auth_service.login(body.email, body.password)
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception as exc:
        logger.warning("Login failed for %s: %s", body.email, exc)
        raise HTTPException(status_code=401, detail=_friendly(exc))


@router.post("/register", status_code=201, response_model=MessageResponse)
@limiter.limit("3/minute", key_func=get_remote_address)
async def register(request: Request, body: RegisterRequest):
    try:
        await auth_service.register(body.email, body.password, body.full_name)
        return MessageResponse(message="Cuenta creada. Revisa tu email para confirmar.")
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly(exc))


@router.post("/logout", response_model=MessageResponse)
async def logout(authorization: str | None = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    await auth_service.logout(token)
    return MessageResponse(message="Sesion cerrada.")


@router.get("/me", response_model=AuthUser)
async def me(user: CurrentUser):
    return user


@router.put("/me/location", response_model=AuthUser)
async def update_location(body: ApproximateLocationRequest, token: CurrentToken, _: CurrentUser):
    try:
        return await auth_service.update_approximate_location(
            token=token,
            latitude=body.latitude,
            longitude=body.longitude,
            label=body.label,
        )
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception as exc:
        logger.error("Location update error: %s", exc)
        raise HTTPException(status_code=400, detail="No se pudo guardar la ubicacion aproximada.")


@router.post("/onboarding", response_model=AuthUser)
async def complete_onboarding(body: OnboardingRequest, token: CurrentToken, _: CurrentUser):
    try:
        return await auth_service.complete_onboarding(token, body.model_dump(exclude_none=True))
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception as exc:
        logger.error("Onboarding error: %s", exc)
        raise HTTPException(status_code=400, detail="No se pudo guardar la configuracion.")


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute", key_func=get_remote_address)
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    redirect_url = f"{request.base_url}reset-password"
    try:
        await auth_service.forgot_password(body.email, redirect_url)
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception as exc:
        logger.error("Forgot password error for %s: %s", body.email, exc)
    return MessageResponse(
        message="Si el correo existe, recibiras instrucciones para recuperar tu cuenta."
    )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute", key_func=get_remote_address)
async def reset_password(request: Request, body: ResetPasswordRequest):
    try:
        await auth_service.reset_password(body.access_token, body.new_password)
        return MessageResponse(message="Contrasena actualizada correctamente.")
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception as exc:
        logger.error("Reset password error: %s", exc)
        raise HTTPException(status_code=400, detail="Token invalido o expirado.")


@router.post("/verify-registration-otp", response_model=AuthResponse)
@limiter.limit("10/minute", key_func=get_remote_address)
async def verify_registration_otp(request: Request, body: VerifyRegistrationOtpRequest):
    try:
        return await auth_service.verify_registration_otp(body.email, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception:
        logger.exception("OTP verification failed")
        raise HTTPException(status_code=400, detail="No se pudo verificar el codigo.")


@router.post("/verify-reset-otp", response_model=MessageResponse)
@limiter.limit("10/minute", key_func=get_remote_address)
async def verify_reset_otp(request: Request, body: VerifyResetOtpRequest):
    try:
        reset_token = await auth_service.verify_reset_otp(body.email, body.code)
        return MessageResponse(message=reset_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Reset OTP verification failed")
        raise HTTPException(status_code=400, detail="Codigo incorrecto o expirado.")


@router.post("/reset-password-otp", response_model=MessageResponse)
@limiter.limit("5/minute", key_func=get_remote_address)
async def reset_password_otp(request: Request, body: ResetPasswordOtpRequest):
    try:
        await auth_service.reset_password_with_otp_token(body.reset_token, body.new_password)
        return MessageResponse(message="Contrasena actualizada correctamente.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except Exception:
        logger.exception("OTP password reset failed")
        raise HTTPException(status_code=400, detail="No se pudo restablecer la contrasena.")
