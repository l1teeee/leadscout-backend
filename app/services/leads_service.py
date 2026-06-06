import logging

from app.exceptions import LeadNotFoundError
from app.repositories import leads_repository
from app.schemas.common import PaginationParams
from app.schemas.lead_schema import LeadCreate, LeadFilters, LeadUpdate

logger = logging.getLogger(__name__)


async def _invalidate_reports(workspace_id: str) -> None:
    from app.services import reports_service
    await reports_service.invalidate(workspace_id)


async def list_leads(workspace_id: str, filters: LeadFilters, pagination: PaginationParams) -> dict:
    return leads_repository.list_leads(
        workspace_id=workspace_id,
        q=filters.q,
        status=filters.status.value if filters.status else None,
        priority=filters.priority.value if filters.priority else None,
        category=filters.category,
        min_score=filters.min_score,
        max_score=filters.max_score,
        limit=pagination.limit,
        offset=pagination.offset,
    )


async def get_lead(workspace_id: str, lead_id: str) -> dict:
    lead = leads_repository.get_lead(lead_id, workspace_id=workspace_id)
    if not lead:
        raise LeadNotFoundError(lead_id)
    return lead


async def create_lead(workspace_id: str, data: LeadCreate) -> dict:
    payload = data.model_dump(mode="json")
    logger.info("Creating lead '%s' in workspace %s", data.name, workspace_id)
    result = leads_repository.create_lead(workspace_id, payload)
    await _invalidate_reports(workspace_id)
    return result


async def update_lead(workspace_id: str, lead_id: str, data: LeadUpdate) -> dict:
    payload = data.model_dump(mode="json", exclude_none=True)
    updated = leads_repository.update_lead(lead_id, payload, workspace_id=workspace_id)
    if not updated:
        raise LeadNotFoundError(lead_id)
    await _invalidate_reports(workspace_id)
    return updated


async def delete_lead(workspace_id: str, lead_id: str) -> None:
    if not leads_repository.delete_lead(lead_id, workspace_id=workspace_id):
        raise LeadNotFoundError(lead_id)
    await _invalidate_reports(workspace_id)
    logger.info("Deleted lead %s", lead_id)
