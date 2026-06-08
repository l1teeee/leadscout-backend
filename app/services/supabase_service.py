from app.config import settings

_client = None


def initialize() -> None:
    """Eagerly create the Supabase client at startup."""
    global _client
    if settings.supabase_configured and _client is None:
        from supabase import create_client
        _client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value(),
        )


def get_client():
    global _client
    if not settings.supabase_configured:
        return None
    if _client is None:
        initialize()
    return _client
