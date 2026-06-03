from typing import Optional
from app.services import supabase_service

_MOCK_WORKSPACE = {
    "id": "mock-workspace-id",
    "name": "LeadScout Demo",
    "slug": "leadscout-demo",
    "country": "El Salvador",
    "timezone": "America/El_Salvador",
    "currency": "USD",
}


def get_workspace(workspace_id: str) -> Optional[dict]:
    db = supabase_service.get_client()
    if db:
        result = db.table("workspaces").select("*").eq("id", workspace_id).maybe_single().execute()
        return result.data
    return _MOCK_WORKSPACE
