import logging
from datetime import UTC, datetime

from app.services import supabase_service

logger = logging.getLogger(__name__)


def _month_start_iso() -> str:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def log_search(
    user_id: str,
    workspace_id: str,
    query: str,
    location: str,
    category: str,
    radius_km: float,
    latitude: float | None,
    longitude: float | None,
    results_count: int,
    saved_new: int,
) -> None:
    db = supabase_service.get_client()
    if not db:
        logger.debug("Supabase not configured: skipping search audit for user %s", user_id)
        return
    try:
        db.table("search_audit_logs").insert({
            "user_id": user_id,
            "workspace_id": workspace_id,
            "query": query,
            "location": location,
            "category": category,
            "radius_km": radius_km,
            "latitude": latitude,
            "longitude": longitude,
            "results_count": results_count,
            "saved_new": saved_new,
        }).execute()
    except Exception as exc:
        logger.warning("Search audit log insert failed: %s", exc)


def count_searches_this_month(workspace_id: str) -> int:
    db = supabase_service.get_client()
    if not db:
        return 0
    try:
        result = (
            db.table("search_audit_logs")
            .select("id", count="exact")
            .eq("workspace_id", workspace_id)
            .gte("created_at", _month_start_iso())
            .execute()
        )
        return result.count or 0
    except Exception as exc:
        logger.debug("Search count failed: %s", exc)
        return 0


def list_recent(workspace_id: str, limit: int = 10) -> list[dict]:
    db = supabase_service.get_client()
    if not db:
        return []
    try:
        result = (
            db.table("search_audit_logs")
            .select("query, location, category, results_count, created_at")
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.debug("Recent search audit fetch failed: %s", exc)
        return []
