import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class LeadNotFoundError(Exception):
    def __init__(self, lead_id: str) -> None:
        self.lead_id = lead_id


class DuplicateLeadError(Exception):
    def __init__(self, identifier: str) -> None:
        self.identifier = identifier


class ExternalServiceError(Exception):
    def __init__(self, service: str, message: str) -> None:
        self.service = service
        self.message = message


class WorkspaceNotFoundError(Exception):
    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id


class ProfileUpdateError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


async def lead_not_found_handler(request: Request, exc: LeadNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"Lead {exc.lead_id} not found"})


async def duplicate_lead_handler(request: Request, exc: DuplicateLeadError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": f"Duplicate lead: {exc.identifier}"})


async def external_service_handler(request: Request, exc: ExternalServiceError) -> JSONResponse:
    logger.error("External service error [%s]: %s", exc.service, exc.message)
    return JSONResponse(
        status_code=502,
        content={"detail": f"{exc.service}: {exc.message}"},
    )
