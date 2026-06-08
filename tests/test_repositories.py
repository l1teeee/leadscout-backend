import pytest
from unittest.mock import MagicMock, patch


def test_delete_lead_returns_false_when_not_found():
    mock_db = MagicMock()
    # delete().eq(id).eq(workspace_id).execute()
    mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    with patch("app.services.supabase_service.get_client", return_value=mock_db):
        import importlib
        from app.repositories import leads_repository
        importlib.reload(leads_repository)
        result = leads_repository.delete_lead("nonexistent-id", workspace_id="ws-123")
    assert result is False


def test_delete_lead_returns_true_when_found():
    mock_db = MagicMock()
    mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "found-id"}])
    with patch("app.services.supabase_service.get_client", return_value=mock_db):
        from app.repositories import leads_repository
        result = leads_repository.delete_lead("found-id", workspace_id="ws-123")
    assert result is True


def test_list_all_selects_only_needed_columns():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    with patch("app.services.supabase_service.get_client", return_value=mock_db):
        from app.repositories import leads_repository
        leads_repository.list_all("ws-123")
    mock_db.table.return_value.select.assert_called_once_with("score,priority,status,category,created_at")


def test_get_workspace_stats_returns_correct_keys():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[
        {"score": 80, "priority": "alta", "last_contact": None, "status": "nuevo"},
        {"score": 40, "priority": "media", "last_contact": "2025-01-01", "status": "contactado"},
    ])
    with patch("app.services.supabase_service.get_client", return_value=mock_db):
        from app.repositories import leads_repository
        stats = leads_repository.get_workspace_stats("ws-123")
    assert "total" in stats
    assert "high_priority_count" in stats
    assert "no_contact_count" in stats
    assert "avg_score" in stats
    assert stats["total"] == 2
    assert stats["high_priority_count"] == 1


def test_find_by_place_id_filters_workspace():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    with patch("app.services.supabase_service.get_client", return_value=mock_db):
        from app.repositories import leads_repository
        result = leads_repository.find_by_place_id("place-abc", "ws-123")
    # Verify both eq calls were made (place_id and workspace_id)
    first_eq = mock_db.table.return_value.select.return_value.eq
    second_eq = first_eq.return_value.eq
    first_eq.assert_called_once_with("google_place_id", "place-abc")
    second_eq.assert_called_once_with("workspace_id", "ws-123")
    assert result is None
