from app.config import settings

_client = None


def get_client():
    global _client
    if not settings.supabase_configured:
        return None
    if _client is None:
        from supabase import create_client
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _client
