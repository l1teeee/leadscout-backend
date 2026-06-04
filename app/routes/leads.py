from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas.enums import LeadPriority, LeadStatus
from app.schemas.lead_schema import LeadCreate, LeadFilters, LeadListResponse, LeadResponse, LeadUpdate
from app.schemas.common import PaginationParams
from app.services import auth_service, leads_service

router = APIRouter(prefix="/leads", tags=["leads"])


async def _get_workspace(authorization: Optional[str]) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    user = await auth_service.get_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    if not user.workspace_id:
        raise HTTPException(status_code=403, detail="Completa el onboarding para crear tu workspace.")
    return user.workspace_id


@router.get("", response_model=LeadListResponse)
async def list_leads(
    authorization: Optional[str] = Header(None),
    q: Optional[str] = Query(None, max_length=200),
    status: Optional[LeadStatus] = Query(None),
    priority: Optional[LeadPriority] = Query(None),
    category: Optional[str] = Query(None, max_length=100),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    workspace_id = await _get_workspace(authorization)
    filters = LeadFilters(
        q=q, status=status, priority=priority,
        category=category, min_score=min_score, max_score=max_score,
    )
    pagination = PaginationParams(limit=limit, offset=offset)
    return await leads_service.list_leads(workspace_id, filters, pagination)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: str, authorization: Optional[str] = Header(None)):
    workspace_id = await _get_workspace(authorization)
    return await leads_service.get_lead(workspace_id, lead_id)


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(body: LeadCreate, authorization: Optional[str] = Header(None)):
    workspace_id = await _get_workspace(authorization)
    return await leads_service.create_lead(workspace_id, body)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: str, body: LeadUpdate, authorization: Optional[str] = Header(None)):
    workspace_id = await _get_workspace(authorization)
    return await leads_service.update_lead(workspace_id, lead_id, body)


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: str, authorization: Optional[str] = Header(None)):
    workspace_id = await _get_workspace(authorization)
    await leads_service.delete_lead(workspace_id, lead_id)
