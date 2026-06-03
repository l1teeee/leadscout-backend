"""Force mock mode during tests regardless of .env configuration."""
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_supabase():
    """Patch supabase_service so tests never hit the real Supabase."""
    with patch("app.services.supabase_service.get_client", return_value=None):
        yield
