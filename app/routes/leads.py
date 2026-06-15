import asyncio
from typing import Optional

from fastapi import APIRouter, Query, Request

from app.dependencies import CurrentWorkspace
from app.rate_limit import limiter
from app.repositories import leads_repository
from app.schemas.common import MAX_PAGE_LIMIT, PaginationParams
from app.schemas.enums import LeadPriority, LeadStatus
from app.schemas.lead_schema import LeadCreate, LeadFilters, LeadListResponse, LeadQualityCheckRequest, LeadQualityCheckResponse, LeadResponse, LeadUpdate
from app.services import ai_service, leads_service

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=LeadListResponse)
async def list_leads(
    workspace_id: CurrentWorkspace,
    q: Optional[str] = Query(None, max_length=200),
    status: Optional[LeadStatus] = Query(None),
    priority: Optional[LeadPriority] = Query(None),
    category: Optional[str] = Query(None, max_length=100),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    sort_by: Optional[str] = Query("created_at", max_length=50),
    sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
    is_viewed: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
):
    filters = LeadFilters(
        q=q, status=status, priority=priority,
        category=category, min_score=min_score, max_score=max_score,
        sort_by=sort_by, sort_order=sort_order, is_viewed=is_viewed,
    )
    pagination = PaginationParams(limit=limit, offset=offset)
    return await leads_service.list_leads(workspace_id, filters, pagination)


@router.get("/stats")
async def get_lead_stats(workspace_id: CurrentWorkspace):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: leads_repository.get_workspace_stats(workspace_id),
    )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: str, workspace_id: CurrentWorkspace):
    return await leads_service.get_lead(workspace_id, lead_id)


@router.post("", response_model=LeadResponse, status_code=201)
@limiter.limit("20/minute")
async def create_lead(request: Request, body: LeadCreate, workspace_id: CurrentWorkspace):
    return await leads_service.create_lead(workspace_id, body)


@router.patch("/{lead_id}", response_model=LeadResponse)
@limiter.limit("20/minute")
async def update_lead(request: Request, lead_id: str, body: LeadUpdate, workspace_id: CurrentWorkspace):
    return await leads_service.update_lead(workspace_id, lead_id, body)


@router.post("/quality-check", response_model=LeadQualityCheckResponse)
@limiter.limit("5/minute")
async def quality_check(request: Request, body: LeadQualityCheckRequest, workspace_id: CurrentWorkspace):
    leads_data = [l.model_dump() for l in body.leads]
    junk_ids = await ai_service.check_lead_quality(leads_data)
    return LeadQualityCheckResponse(junk_ids=junk_ids)


@router.delete("/{lead_id}", status_code=204)
@limiter.limit("20/minute")
async def delete_lead(request: Request, lead_id: str, workspace_id: CurrentWorkspace):
    await leads_service.delete_lead(workspace_id, lead_id)
