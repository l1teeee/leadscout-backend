from app.config import settings

_client = None


def _create_service_role_client():
    from supabase import ClientOptions, create_client

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value(),
        options=ClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


def initialize() -> None:
    """Eagerly create the Supabase admin client at startup."""
    global _client
    if settings.supabase_configured and _client is None:
        _client = _create_service_role_client()


def get_client():
    global _client
    if not settings.supabase_configured:
        return None
    if _client is None:
        initialize()
    return _client


def get_auth_client():
    """Return an isolated Supabase client for auth flows that may emit sessions."""
    if not settings.supabase_configured:
        return None
    return _create_service_role_client()
