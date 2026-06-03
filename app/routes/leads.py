from typing import Optional

from fastapi import APIRouter, Query

from app.schemas.enums import LeadPriority, LeadStatus
from app.schemas.lead_schema import LeadCreate, LeadFilters, LeadListResponse, LeadResponse, LeadUpdate
from app.schemas.common import PaginationParams
from app.services import leads_service

router = APIRouter(prefix="/leads", tags=["leads"])

_WORKSPACE = "mock-workspace-id"


@router.get("", response_model=LeadListResponse)
async def list_leads(
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
    return await leads_service.list_leads(_WORKSPACE, filters, pagination)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: str):
    return await leads_service.get_lead(_WORKSPACE, lead_id)


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(body: LeadCreate):
    return await leads_service.create_lead(_WORKSPACE, body)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: str, body: LeadUpdate):
    return await leads_service.update_lead(_WORKSPACE, lead_id, body)


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: str):
    await leads_service.delete_lead(_WORKSPACE, lead_id)
