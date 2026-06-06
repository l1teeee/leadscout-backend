from fastapi import APIRouter

from app.dependencies import CurrentWorkspace
from app.services import reports_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
async def get_summary(workspace_id: CurrentWorkspace):
    return await reports_service.get_summary(workspace_id)
