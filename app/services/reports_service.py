import logging
from datetime import date as _date
from datetime import datetime, timedelta, timezone

from app.async_utils import run_sync
from app.cache import TTL_REPORTS, cache
from app.repositories import leads_repository

logger = logging.getLogger(__name__)


async def get_summary(workspace_id: str) -> dict:
    key = f"reports:summary:{workspace_id}"
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: %s", key)
        return cached

    result = await _compute_summary(workspace_id)
    await cache.set(key, result, ttl=TTL_REPORTS)
    return result


async def invalidate(workspace_id: str) -> None:
    await cache.invalidate_prefix(f"reports:summary:{workspace_id}")
    for days in (7, 30, 90, "all"):
        await cache.invalidate_prefix(f"reports:timeline:{workspace_id}:{days}")


async def get_timeline(workspace_id: str, days: int) -> dict:
    days = days if days in (7, 30, 90) else 30
    key = f"reports:timeline:{workspace_id}:{days}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    leads = await run_sync(leads_repository.list_all, workspace_id)
    result = {"days": days, "points": _daily_activity(leads, days)}
    await cache.set(key, result, ttl=TTL_REPORTS)
    return result


async def _compute_summary(workspace_id: str) -> dict:
    leads = await run_sync(leads_repository.list_all, workspace_id)
    total = len(leads)
    avg_score = round(sum(r["score"] for r in leads) / total) if total else 0

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_this_week = sum(1 for r in leads if (r.get("created_at") or "") >= week_ago)
    contacted = sum(1 for r in leads if r["status"] == "contactado")

    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_category: dict[str, int] = {}

    for r in leads:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_priority[r["priority"]] = by_priority.get(r["priority"], 0) + 1
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1

    return {
        "total_leads": total,
        "new_this_week": new_this_week,
        "contacted": contacted,
        "avg_score": avg_score,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_category": by_category,
        "weekly_activity": _weekly_activity(leads),
    }


def _weekly_activity(leads: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    return [
        {
            "date": (day := today - timedelta(days=i)).isoformat(),
            "leads": sum(1 for r in leads if (r.get("created_at") or "")[:10] == day.isoformat()),
        }
        for i in range(6, -1, -1)
    ]


def _daily_activity(leads: list[dict], days: int) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    return [
        {
            "date": (day := today - timedelta(days=i)).isoformat(),
            "leads": sum(1 for r in leads if (r.get("created_at") or "")[:10] == day.isoformat()),
        }
        for i in range(days - 1, -1, -1)
    ]


async def get_timeline_all(workspace_id: str) -> dict:
    key = f"reports:timeline:{workspace_id}:all"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    leads = await run_sync(leads_repository.list_all, workspace_id)
    result = {"days": None, "points": _all_time_activity(leads)}
    await cache.set(key, result, ttl=TTL_REPORTS)
    return result


def _all_time_activity(leads: list[dict]) -> list[dict]:
    if not leads:
        return []
    dates = [r.get("created_at", "")[:10] for r in leads if r.get("created_at")]
    if not dates:
        return []
    start = _date.fromisoformat(min(dates))
    today = datetime.now(timezone.utc).date()
    total_days = (today - start).days + 1
    return [
        {
            "date": (day := today - timedelta(days=i)).isoformat(),
            "leads": sum(1 for r in leads if (r.get("created_at") or "")[:10] == day.isoformat()),
        }
        for i in range(total_days - 1, -1, -1)
    ]
