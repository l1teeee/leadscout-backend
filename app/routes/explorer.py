from fastapi import APIRouter, HTTPException, Request

from app.dependencies import CurrentUser, CurrentWorkspace
from app.exceptions import ExternalServiceError
from app.rate_limit import limiter
from app.schemas.explorer_schema import (
    ExplorerSearchRequest,
    ExplorerSearchResponse,
    LeadAnalyzeRequest,
    LeadAnalyzeResponse,
)
from app.services import ai_service, explorer_service

router = APIRouter(prefix="/explorer", tags=["explorer"])


@router.post("/search", response_model=ExplorerSearchResponse)
@limiter.limit("30/minute")
async def search(request: Request, body: ExplorerSearchRequest, user: CurrentUser, workspace_id: CurrentWorkspace):
    try:
        return await explorer_service.search_and_save(workspace_id, user.id, body)
    except ExternalServiceError as exc:
        raise HTTPException(status_code=503, detail=f"{exc.service}: {exc.message}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}")


@router.post("/analyze", response_model=LeadAnalyzeResponse)
@limiter.limit("20/minute")
async def analyze(request: Request, body: LeadAnalyzeRequest, user: CurrentUser, workspace_id: CurrentWorkspace):
    try:
        analysis = await ai_service.analyze_lead(body.model_dump())
        return LeadAnalyzeResponse(analysis=analysis)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {exc}")
