from typing import Optional

from fastapi import APIRouter, Query, Request

from app.dependencies import CurrentWorkspace
from app.rate_limit import limiter
from app.schemas.common import PaginationParams
from app.schemas.enums import LeadPriority, LeadStatus
from app.schemas.lead_schema import LeadCreate, LeadFilters, LeadListResponse, LeadResponse, LeadUpdate
from app.services import leads_service

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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    filters = LeadFilters(
        q=q, status=status, priority=priority,
        category=category, min_score=min_score, max_score=max_score,
    )
    pagination = PaginationParams(limit=limit, offset=offset)
    return await leads_service.list_leads(workspace_id, filters, pagination)


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


@router.delete("/{lead_id}", status_code=204)
@limiter.limit("20/minute")
async def delete_lead(request: Request, lead_id: str, workspace_id: CurrentWorkspace):
    await leads_service.delete_lead(workspace_id, lead_id)
