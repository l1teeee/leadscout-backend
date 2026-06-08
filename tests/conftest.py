import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_current_user, get_current_workspace
from app.schemas.auth_schema import AuthUser

TEST_WORKSPACE_ID = "test-workspace-123"
TEST_USER = AuthUser(
    id="test-user-456",
    email="test@leadscout.dev",
    full_name="Test User",
    role="owner",
    onboarded=True,
    workspace_id=TEST_WORKSPACE_ID,
)

MOCK_LEAD = {
    "id": "mock-lead-id",
    "workspace_id": TEST_WORKSPACE_ID,
    "name": "Test Business",
    "category": "Servicios",
    "location": "San Salvador",
    "address": None,
    "latitude": None,
    "longitude": None,
    "score": 50,
    "status": "nuevo",
    "priority": "media",
    "issues": [],
    "phone": None,
    "website": None,
    "google_place_id": None,
    "source": "manual",
    "last_contact": None,
    "ai_analysis": None,
    "is_viewed": False,
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-01T00:00:00",
}

MOCK_WORKSPACE = {
    "id": TEST_WORKSPACE_ID,
    "name": "Test Workspace",
    "slug": "test-workspace",
    "country": "El Salvador",
    "industry": None,
    "city": None,
    "phone": None,
    "website": None,
    "timezone": "UTC",
    "currency": "USD",
}


@pytest.fixture(autouse=True)
def override_dependencies():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_current_workspace] = lambda: TEST_WORKSPACE_ID
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_supabase():
    mock_db = MagicMock()
    _tables: dict[str, MagicMock] = {}

    def _make_leads_mock() -> MagicMock:
        m = MagicMock()
        empty = MagicMock(data=[], count=0)

        m.select.return_value.eq.return_value.execute.return_value = empty
        m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = empty
        m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
        m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
        m.select.return_value.eq.return_value.eq.return_value.execute.return_value = empty

        # insert: echo back the inserted data so create_lead returns the real payload
        def _insert_se(data):
            inner = MagicMock()
            inner.execute.return_value = MagicMock(data=[data])
            return inner

        m.insert.side_effect = _insert_se

        # update/delete: default not-found (data=[]) — tests that need success override these
        m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        m.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        m.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        m.upsert.return_value.execute.return_value = MagicMock(data=[])
        return m

    def _make_workspace_mock() -> MagicMock:
        m = MagicMock()
        m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=MOCK_WORKSPACE)
        m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[MOCK_WORKSPACE])
        m.insert.return_value.execute.return_value = MagicMock(data=[MOCK_WORKSPACE])
        return m

    def _make_default_mock() -> MagicMock:
        m = MagicMock()
        m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
        m.insert.return_value.execute.return_value = MagicMock(data=[])
        m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        m.upsert.return_value.execute.return_value = MagicMock(data=[])
        return m

    def _table_factory(name: str) -> MagicMock:
        if name not in _tables:
            if name == "leads":
                _tables[name] = _make_leads_mock()
            elif name == "workspaces":
                _tables[name] = _make_workspace_mock()
            else:
                _tables[name] = _make_default_mock()
        return _tables[name]

    mock_db.table.side_effect = _table_factory
    # backward compat: tests that use mock_supabase.table.return_value.xxx get the leads mock
    mock_db.table.return_value = _table_factory("leads")

    with patch("app.services.supabase_service.get_client", return_value=mock_db):
        yield mock_db


@pytest.fixture
def client():
    return TestClient(app)
