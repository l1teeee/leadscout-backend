from fastapi import APIRouter

from app.services import reports_service

router = APIRouter(prefix="/reports", tags=["reports"])

_WORKSPACE = "mock-workspace-id"


@router.get("/summary")
async def get_summary():
    return await reports_service.get_summary(_WORKSPACE)
