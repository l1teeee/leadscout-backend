from app.config import settings


def get_client():
    if not settings.supabase_configured:
        return None
    from supabase import create_client
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
