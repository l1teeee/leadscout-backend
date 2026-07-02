from fastapi import APIRouter, HTTPException, Request
from slowapi.util import get_remote_address

from app.exceptions import SupportRequestError
from app.rate_limit import limiter
from app.schemas.auth_schema import MessageResponse
from app.schemas.settings_schema import PublicSupportContactRequest
from app.services import settings_service

router = APIRouter(prefix="/support", tags=["support"])


@router.post("", response_model=MessageResponse)
@limiter.limit("3/minute", key_func=get_remote_address)
async def send_public_support_request(request: Request, body: PublicSupportContactRequest):
    try:
        await settings_service.send_public_support_request(body)
    except SupportRequestError as exc:
        raise HTTPException(status_code=502, detail=exc.message)
    return MessageResponse(message="Consulta enviada.")
