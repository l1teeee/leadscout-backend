from fastapi import APIRouter

from app.repositories import workspaces_repository

router = APIRouter(prefix="/settings", tags=["settings"])

_MOCK_TEAM = [
    {"id": "u1", "full_name": "Admin LeadScout", "email": "admin@leadscout.io", "role": "owner", "avatar_url": None},
    {"id": "u2", "full_name": "Sales Rep", "email": "sales@leadscout.io", "role": "sales", "avatar_url": None},
]

_MOCK_USAGE = {
    "leads_used": 148,
    "leads_limit": 500,
    "searches_used": 23,
    "searches_limit": 100,
    "api_calls_used": 71,
    "api_calls_limit": 1000,
}


@router.get("/workspace")
def get_workspace():
    return workspaces_repository.get_workspace("mock-workspace-id")


@router.get("/team")
def get_team():
    return {"members": _MOCK_TEAM}


@router.get("/usage")
def get_usage():
    return _MOCK_USAGE
