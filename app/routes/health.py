import logging

from fastapi import APIRouter

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    checks: dict[str, str] = {}

    try:
        from app.services.supabase_service import get_client
        client = get_client()
        if client is None:
            checks["supabase"] = "not_configured"
        else:
            client.table("workspaces").select("id").limit(1).execute()
            checks["supabase"] = "ok"
    except Exception as exc:
        logger.warning("Supabase health check failed: %s", exc)
        checks["supabase"] = "error"

    try:
        from app.cache import _RedisCache, cache
        if isinstance(cache, _RedisCache):
            await cache._client.ping()
            checks["cache"] = "redis:ok"
        else:
            checks["cache"] = "in-memory"
    except Exception as exc:
        logger.warning("Cache health check failed: %s", exc)
        checks["cache"] = "error"

    status = "degraded" if {"error", "not_configured"} & set(checks.values()) else "ok"
    return {
        "status": status,
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
        "checks": checks,
    }
