from unittest.mock import MagicMock, patch

from app.services.social_scraper_service import _dedupe_profiles

LEAD_BASE = {
    "id": "lead-001",
    "workspace_id": "test-workspace-123",
    "name": "Test Business",
    "category": "Servicios",
    "location": "San Salvador",
    "score": 60,
    "status": "nuevo",
    "priority": "media",
    "issues": [],
    "source": "manual",
    "is_viewed": False,
    "ai_analysis": None,
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-01T00:00:00",
}


def test_patch_lead_sets_is_viewed(client, mock_supabase):
    updated_lead = {**LEAD_BASE, "is_viewed": True, "updated_at": "2025-01-02T00:00:00"}
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[updated_lead])
    response = client.patch("/api/leads/lead-001", json={"is_viewed": True})
    assert response.status_code == 200
    assert response.json()["is_viewed"] is True


def test_patch_lead_not_found_returns_404(client, mock_supabase):
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    response = client.patch("/api/leads/nonexistent", json={"status": "contactado"})
    assert response.status_code == 404


def test_analyze_returns_cached_analysis(client, mock_supabase):
    lead_with_analysis = {**LEAD_BASE, "ai_analysis": "Analisis previo cacheado"}
    # get_lead: select("*").eq("id", ...).eq("workspace_id", ...).maybe_single().execute()
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=lead_with_analysis)
    response = client.post("/api/explorer/analyze", json={
        "name": "Test Business",
        "category": "Servicios",
        "location": "San Salvador",
        "score": 60,
        "issues": [],
        "lead_id": "lead-001",
    })
    assert response.status_code == 200
    assert response.json()["analysis"] == "Analisis previo cacheado"


def test_analyze_calls_openai_when_no_cache(client, mock_supabase):
    # get_lead returns lead with no ai_analysis
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={**LEAD_BASE, "ai_analysis": None})
    updated = {**LEAD_BASE, "ai_analysis": "Nuevo analisis"}
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[updated])

    with patch("app.services.ai_service.analyze_lead_with_social", return_value={"analysis": "Nuevo analisis", "social_profiles": []}) as mock_ai:
        response = client.post("/api/explorer/analyze", json={
            "name": "Test Business",
            "category": "Servicios",
            "location": "San Salvador",
            "score": 60,
            "issues": [],
            "lead_id": "lead-001",
        })
    assert response.status_code == 200
    assert response.json()["analysis"] == "Nuevo analisis"
    mock_ai.assert_called_once()


def test_analyze_force_refresh_ignores_cached_analysis(client, mock_supabase):
    lead_with_analysis = {
        **LEAD_BASE,
        "website": "https://example.com",
        "phone": "2222-2222",
        "ai_analysis": "Analisis viejo",
    }
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=lead_with_analysis)
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{**lead_with_analysis, "ai_analysis": "Analisis nuevo"}]
    )

    with patch("app.services.ai_service.analyze_lead_with_social", return_value={"analysis": "Analisis nuevo", "social_profiles": []}) as mock_ai:
        response = client.post("/api/explorer/analyze", json={
            "name": "Test Business",
            "category": "Servicios",
            "location": "San Salvador",
            "score": 60,
            "issues": [],
            "lead_id": "lead-001",
            "force_refresh": True,
        })

    assert response.status_code == 200
    assert response.json()["analysis"] == "Analisis nuevo"
    mock_ai.assert_called_once()
    payload = mock_ai.call_args.args[0]
    assert payload["website"] == "https://example.com"
    assert payload["phone"] == "2222-2222"


def test_social_profile_dedupe_skips_share_links():
    profiles = _dedupe_profiles([
        "https://www.facebook.com/sharer/sharer.php?u=https://example.com",
        "https://instagram.com/teosrestaurante?utm_source=site",
        "https://www.tiktok.com/@teosrestaurante",
        "https://instagram.com/teosrestaurante",
    ])

    assert profiles == [
        {"platform": "instagram", "url": "https://instagram.com/teosrestaurante"},
        {"platform": "tiktok", "url": "https://www.tiktok.com/@teosrestaurante"},
    ]
