from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.seeds.seed_data import SEED_LEADS
from app.services import supabase_service

_mock_store: list[dict] = list(SEED_LEADS)

DEFAULT_WORKSPACE_ID = "mock-workspace-id"


def _db():
    return supabase_service.get_client()


def _apply_mock_filters(
    data: list[dict],
    q: Optional[str],
    status: Optional[str],
    priority: Optional[str],
    category: Optional[str],
    min_score: Optional[int],
    max_score: Optional[int],
) -> list[dict]:
    if q:
        ql = q.lower()
        data = [
            r for r in data
            if ql in r["name"].lower()
            or ql in (r.get("location") or "").lower()
            or ql in (r.get("address") or "").lower()
        ]
    if status:
        data = [r for r in data if r["status"] == status]
    if priority:
        data = [r for r in data if r["priority"] == priority]
    if category:
        data = [r for r in data if r["category"] == category]
    if min_score is not None:
        data = [r for r in data if r["score"] >= min_score]
    if max_score is not None:
        data = [r for r in data if r["score"] <= max_score]
    return data


def list_leads(
    workspace_id: str,
    q: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    db = _db()
    if db:
        query = db.table("leads").select("*", count="exact").eq("workspace_id", workspace_id)
        if status:
            query = query.eq("status", status)
        if priority:
            query = query.eq("priority", priority)
        if category:
            query = query.eq("category", category)
        if min_score is not None:
            query = query.gte("score", min_score)
        if max_score is not None:
            query = query.lte("score", max_score)
        result = query.range(offset, offset + limit - 1).execute()
        data = result.data
        if q:
            ql = q.lower()
            data = [r for r in data if ql in r["name"].lower() or ql in (r.get("address") or "").lower()]
        return {"data": data, "total": result.count or len(data), "limit": limit, "offset": offset}

    filtered = _apply_mock_filters(list(_mock_store), q, status, priority, category, min_score, max_score)
    total = len(filtered)
    page = filtered[offset: offset + limit]
    return {"data": page, "total": total, "limit": limit, "offset": offset}


def list_all(workspace_id: str) -> list[dict]:
    """Used internally for aggregations - no pagination."""
    db = _db()
    if db:
        return db.table("leads").select("*").eq("workspace_id", workspace_id).execute().data
    return list(_mock_store)


def get_lead(lead_id: str) -> Optional[dict]:
    db = _db()
    if db:
        result = db.table("leads").select("*").eq("id", lead_id).maybe_single().execute()
        return result.data
    return next((r for r in _mock_store if r["id"] == lead_id), None)


def create_lead(workspace_id: str, data: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    lead = {"id": str(uuid4()), "workspace_id": workspace_id, "created_at": now, "updated_at": now, **data}
    db = _db()
    if db:
        return db.table("leads").insert(lead).execute().data[0]
    _mock_store.append(lead)
    return lead


def update_lead(lead_id: str, data: dict) -> Optional[dict]:
    data = {**data, "updated_at": datetime.now(timezone.utc).isoformat()}
    db = _db()
    if db:
        result = db.table("leads").update(data).eq("id", lead_id).execute()
        return result.data[0] if result.data else None
    for i, r in enumerate(_mock_store):
        if r["id"] == lead_id:
            _mock_store[i] = {**r, **data}
            return _mock_store[i]
    return None


def delete_lead(lead_id: str) -> bool:
    db = _db()
    if db:
        db.table("leads").delete().eq("id", lead_id).execute()
        return True
    for i, r in enumerate(_mock_store):
        if r["id"] == lead_id:
            _mock_store.pop(i)
            return True
    return False


def find_by_place_id(google_place_id: str) -> Optional[dict]:
    db = _db()
    if db:
        result = db.table("leads").select("id").eq("google_place_id", google_place_id).execute()
        return result.data[0] if result.data else None
    return next((r for r in _mock_store if r.get("google_place_id") == google_place_id), None)
