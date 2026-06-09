from fastapi import APIRouter, HTTPException, Request

from app.async_utils import run_sync
from app.dependencies import CurrentUser, CurrentWorkspace
from app.exceptions import ExternalServiceError
from app.rate_limit import limiter
from app.repositories import leads_repository
from app.schemas.explorer_schema import (
    ExplorerSearchRequest,
    ExplorerSearchResponse,
    LeadAnalyzeRequest,
    LeadAnalyzeResponse,
    LeadChatRequest,
    LeadChatResponse,
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
        lead = None
        if body.lead_id:
            lead = await run_sync(leads_repository.get_lead, body.lead_id, workspace_id=workspace_id)
            if lead and lead.get("ai_analysis") and not body.force_refresh:
                return LeadAnalyzeResponse(analysis=lead["ai_analysis"])

        request_data = body.model_dump(exclude={"lead_id", "force_refresh"})
        data = {**request_data}
        if lead:
            data = {
                **request_data,
                "name": lead.get("name") or request_data.get("name"),
                "category": lead.get("category") or request_data.get("category"),
                "location": lead.get("location") or request_data.get("location"),
                "phone": lead.get("phone") or request_data.get("phone"),
                "website": lead.get("website") or request_data.get("website"),
                "score": lead.get("score") if lead.get("score") is not None else request_data.get("score"),
                "issues": lead.get("issues") or request_data.get("issues") or [],
                "address": lead.get("address"),
                "google_place_id": lead.get("google_place_id"),
            }

        analysis = await ai_service.analyze_lead(data)

        if body.lead_id:
            await run_sync(leads_repository.update_lead, body.lead_id, {"ai_analysis": analysis}, workspace_id=workspace_id)

        return LeadAnalyzeResponse(analysis=analysis)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {exc}")


@router.post("/chat", response_model=LeadChatResponse)
@limiter.limit("30/minute")
async def chat(request: Request, body: LeadChatRequest, user: CurrentUser, workspace_id: CurrentWorkspace):
    try:
        lead_context = body.model_dump(exclude={"question"})
        if body.lead_id:
            lead = await run_sync(leads_repository.get_lead, body.lead_id, workspace_id=workspace_id)
            if lead:
                lead_context = {**lead_context, **{k: v for k, v in lead.items() if v is not None}}
        answer = await ai_service.ask_lead_question(lead_context, body.question)
        return LeadChatResponse(answer=answer)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {exc}")
