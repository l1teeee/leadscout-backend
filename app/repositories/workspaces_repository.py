
from app.exceptions import ExternalServiceError
from app.services import supabase_service


def _db_required():
    db = supabase_service.get_client()
    if not db:
        raise ExternalServiceError("Supabase", "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
    return db


def get_workspace(workspace_id: str) -> dict | None:
    db = _db_required()
    result = db.table("workspaces").select("*").eq("id", workspace_id).maybe_single().execute()
    return result.data


def update_workspace(workspace_id: str, data: dict) -> dict | None:
    db = _db_required()
    result = db.table("workspaces").update(data).eq("id", workspace_id).execute()
    return result.data[0] if result.data else None


def get_team_members(workspace_id: str) -> list[dict]:
    db = _db_required()
    result = (
        db.table("profiles")
        .select("id, full_name, email, role, avatar_url")
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return result.data or []
