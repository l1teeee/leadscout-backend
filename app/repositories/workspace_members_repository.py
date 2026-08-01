from app.exceptions import ExternalServiceError
from app.services import supabase_service


def _db_required():
    db = supabase_service.get_client()
    if not db:
        raise ExternalServiceError("Supabase", "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
    return db


def list_for_user(user_id: str) -> list[dict]:
    db = _db_required()
    result = (
        db.table("workspace_members")
        .select("workspace_id, role, workspaces(name)")
        .eq("user_id", user_id)
        .execute()
    )
    return result.data or []


def is_member(user_id: str, workspace_id: str) -> bool:
    db = _db_required()
    result = (
        db.table("workspace_members")
        .select("id")
        .eq("user_id", user_id)
        .eq("workspace_id", workspace_id)
        .maybe_single()
        .execute()
    )
    return result is not None and bool(result.data)


def add_member(workspace_id: str, user_id: str, role: str = "owner") -> None:
    db = _db_required()
    db.table("workspace_members").insert({
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role": role,
    }).execute()
