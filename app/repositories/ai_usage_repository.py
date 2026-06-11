import logging
from datetime import UTC, datetime

from app.services import supabase_service

logger = logging.getLogger(__name__)


def _month_start_iso() -> str:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def log_usage(
    workspace_id: str,
    user_id: str | None,
    kind: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    db = supabase_service.get_client()
    if not db:
        logger.debug("Supabase not configured: skipping AI usage log for workspace %s", workspace_id)
        return
    try:
        db.table("ai_usage_logs").insert({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "kind": kind,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }).execute()
    except Exception as exc:
        logger.warning("AI usage log insert failed: %s", exc)


def count_tokens_this_month(workspace_id: str) -> int:
    db = supabase_service.get_client()
    if not db:
        return 0
    try:
        result = (
            db.table("ai_usage_logs")
            .select("total_tokens")
            .eq("workspace_id", workspace_id)
            .gte("created_at", _month_start_iso())
            .execute()
        )
        return sum(int(row.get("total_tokens") or 0) for row in (result.data or []))
    except Exception as exc:
        logger.debug("Token usage count failed: %s", exc)
        return 0
