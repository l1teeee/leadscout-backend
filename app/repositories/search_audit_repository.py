import logging
from typing import Optional

from app.services import supabase_service

logger = logging.getLogger(__name__)


def log_search(
    user_id: str,
    workspace_id: str,
    query: str,
    location: str,
    category: str,
    radius_km: float,
    latitude: Optional[float],
    longitude: Optional[float],
    results_count: int,
    saved_new: int,
) -> None:
    db = supabase_service.get_client()
    if not db:
        logger.debug("Mock mode: skipping search audit for user %s", user_id)
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
