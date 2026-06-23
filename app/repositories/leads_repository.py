import re
from datetime import UTC, datetime
from uuid import uuid4

from app.exceptions import ExternalServiceError
from app.services import supabase_service


def _db_required():
    db = supabase_service.get_client()
    if not db:
        raise ExternalServiceError("Supabase", "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
    return db


def list_leads(
    workspace_id: str,
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    is_viewed: bool | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    db = _db_required()
    query = db.table("leads").select("*", count="exact").eq("workspace_id", workspace_id)
    if status:
        query = query.eq("status", status)
    if priority:
        query = query.eq("priority", priority)
    if category:
        query = query.eq("category", category)
    if q:
        safe_q = re.sub(r"[%,()\\*]", " ", q).strip()
        if safe_q:
            query = query.or_(f"name.ilike.%{safe_q}%,address.ilike.%{safe_q}%")
    if min_score is not None:
        query = query.gte("score", min_score)
    if max_score is not None:
        query = query.lte("score", max_score)
    if is_viewed is not None:
        query = query.eq("is_viewed", is_viewed)
    query = query.order(sort_by, desc=(sort_order == "desc"))
    result = query.range(offset, offset + limit - 1).execute()
    data = result.data
    return {"data": data, "total": result.count or len(data), "limit": limit, "offset": offset}


def list_all(workspace_id: str) -> list[dict]:
    """Used internally for aggregations - no pagination."""
    db = _db_required()
    return (
        db.table("leads")
        .select("score,priority,status,category,created_at")
        .eq("workspace_id", workspace_id)
        .execute()
        .data
    )


def get_lead(lead_id: str, workspace_id: str | None = None) -> dict | None:
    db = _db_required()
    query = db.table("leads").select("*").eq("id", lead_id)
    if workspace_id:
        query = query.eq("workspace_id", workspace_id)
    result = query.maybe_single().execute()
    return result.data


def create_lead(workspace_id: str, data: dict) -> dict:
    now = datetime.now(UTC).isoformat()
    lead = {"id": str(uuid4()), "workspace_id": workspace_id, "created_at": now, "updated_at": now, **data}
    db = _db_required()
    return db.table("leads").insert(lead).execute().data[0]


def update_lead(lead_id: str, data: dict, workspace_id: str | None = None) -> dict | None:
    data = {**data, "updated_at": datetime.now(UTC).isoformat()}
    db = _db_required()
    query = db.table("leads").update(data).eq("id", lead_id)
    if workspace_id:
        query = query.eq("workspace_id", workspace_id)
    result = query.execute()
    return result.data[0] if result.data else None


def delete_lead(lead_id: str, workspace_id: str | None = None) -> bool:
    db = _db_required()
    query = db.table("leads").delete().eq("id", lead_id)
    if workspace_id:
        query = query.eq("workspace_id", workspace_id)
    result = query.execute()
    return bool(result.data)


def find_by_place_id(google_place_id: str, workspace_id: str) -> dict | None:
    db = _db_required()
    result = (
        db.table("leads")
        .select("id")
        .eq("google_place_id", google_place_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_workspace_stats(workspace_id: str) -> dict:
    db = _db_required()
    rows = db.table("leads").select("score,priority,last_contact,status").eq("workspace_id", workspace_id).execute().data or []
    total = len(rows)
    high_priority = sum(1 for r in rows if r.get("priority") == "alta")
    no_contact = sum(1 for r in rows if r.get("status") == "nuevo")
    avg_score = round(sum(r.get("score", 0) for r in rows) / total) if total > 0 else 0
    by_status: dict[str, int] = {}
    for r in rows:
        s = r.get("status", "nuevo")
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "total": total,
        "high_priority_count": high_priority,
        "no_contact_count": no_contact,
        "avg_score": avg_score,
        "by_status": by_status,
    }
