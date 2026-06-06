from typing import Optional

from app.services import supabase_service

_MOCK_WORKSPACE = {
    "id": "mock-workspace-id",
    "name": "LeadScout Demo",
    "slug": "leadscout-demo",
    "country": "El Salvador",
    "industry": None,
    "city": None,
    "phone": None,
    "website": None,
    "timezone": "America/El_Salvador",
    "currency": "USD",
}

_MOCK_TEAM = [
    {
        "id": "mock-user-id",
        "full_name": "Demo User",
        "email": "demo@example.com",
        "role": "owner",
        "avatar_url": None,
    },
]


def get_workspace(workspace_id: str) -> Optional[dict]:
    db = supabase_service.get_client()
    if db:
        result = db.table("workspaces").select("*").eq("id", workspace_id).maybe_single().execute()
        return result.data
    return _MOCK_WORKSPACE


def update_workspace(workspace_id: str, data: dict) -> Optional[dict]:
    db = supabase_service.get_client()
    if db:
        result = db.table("workspaces").update(data).eq("id", workspace_id).execute()
        return result.data[0] if result.data else None
    return {**_MOCK_WORKSPACE, **data}


def get_team_members(workspace_id: str) -> list[dict]:
    db = supabase_service.get_client()
    if db:
        result = (
            db.table("profiles")
            .select("id, full_name, email, role, avatar_url")
            .eq("workspace_id", workspace_id)
            .execute()
        )
        return result.data or []
    return list(_MOCK_TEAM)
