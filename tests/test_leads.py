import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import MOCK_LEAD

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data


def test_list_leads_returns_paginated_shape():
    response = client.get("/api/leads")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert isinstance(data["data"], list)


def test_list_leads_default_limit():
    response = client.get("/api/leads")
    data = response.json()
    assert data["limit"] == 100
    assert data["offset"] == 0


def test_list_leads_pagination():
    response = client.get("/api/leads?limit=3&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) <= 3
    assert data["limit"] == 3


def test_list_leads_invalid_limit_too_large():
    response = client.get("/api/leads?limit=999")
    assert response.status_code == 422


def test_list_leads_invalid_limit_zero():
    response = client.get("/api/leads?limit=0")
    assert response.status_code == 422


def test_list_leads_filter_by_status():
    response = client.get("/api/leads?status=nuevo")
    assert response.status_code == 200
    data = response.json()
    for lead in data["data"]:
        assert lead["status"] == "nuevo"


def test_list_leads_filter_by_invalid_status():
    response = client.get("/api/leads?status=invalido")
    assert response.status_code == 422


def test_list_leads_filter_by_priority():
    response = client.get("/api/leads?priority=alta")
    assert response.status_code == 200
    data = response.json()
    for lead in data["data"]:
        assert lead["priority"] == "alta"


def test_list_leads_filter_score_range():
    response = client.get("/api/leads?min_score=0&max_score=30")
    assert response.status_code == 200
    data = response.json()
    for lead in data["data"]:
        assert 0 <= lead["score"] <= 30


def test_list_leads_invalid_score_above_100():
    response = client.get("/api/leads?min_score=150")
    assert response.status_code == 422


def test_get_lead_not_found():
    response = client.get("/api/leads/nonexistent-00000")
    assert response.status_code == 404


def test_create_lead():
    payload = {
        "name": "Test Negocio SV",
        "category": "Servicios",
        "location": "San Salvador",
        "score": 50,
        "status": "nuevo",
        "priority": "media",
        "issues": ["Sin sitio web"],
        "source": "manual",
    }
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Negocio SV"
    assert data["status"] == "nuevo"
    assert "id" in data
    assert "workspace_id" in data


def test_create_lead_invalid_score():
    payload = {"name": "Bad Lead", "category": "Test", "score": 999}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 422


def test_create_lead_invalid_status():
    payload = {"name": "Bad Lead", "category": "Test", "status": "fantasma"}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 422


def test_create_lead_empty_name():
    payload = {"name": "", "category": "Test"}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 422


def test_update_lead(mock_supabase):
    create_resp = client.post("/api/leads", json={
        "name": "Lead Para Actualizar",
        "category": "Retail",
    })
    assert create_resp.status_code == 201
    lead_id = create_resp.json()["id"]

    updated_lead = {**MOCK_LEAD, "id": lead_id, "status": "contactado"}
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[updated_lead])

    update_resp = client.patch(f"/api/leads/{lead_id}", json={"status": "contactado"})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "contactado"


def test_update_lead_not_found():
    response = client.patch("/api/leads/nonexistent-00000", json={"status": "contactado"})
    assert response.status_code == 404


def test_delete_lead(mock_supabase):
    create_resp = client.post("/api/leads", json={"name": "Lead A Eliminar", "category": "Test"})
    assert create_resp.status_code == 201
    lead_id = create_resp.json()["id"]

    mock_supabase.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": lead_id}])

    delete_resp = client.delete(f"/api/leads/{lead_id}")
    assert delete_resp.status_code == 204

    get_resp = client.get(f"/api/leads/{lead_id}")
    assert get_resp.status_code == 404


def test_delete_lead_not_found():
    response = client.delete("/api/leads/nonexistent-00000")
    assert response.status_code == 404


def test_report_summary_shape():
    response = client.get("/api/reports/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_leads" in data
    assert "avg_score" in data
    assert "by_status" in data
    assert "by_priority" in data
    assert "by_category" in data
    assert "weekly_activity" in data
    assert isinstance(data["weekly_activity"], list)
    assert len(data["weekly_activity"]) == 7


def test_report_summary_values():
    response = client.get("/api/reports/summary")
    data = response.json()
    assert data["total_leads"] >= 0
    assert 0 <= data["avg_score"] <= 100


def test_settings_workspace():
    response = client.get("/api/settings/workspace")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data


def test_settings_team():
    response = client.get("/api/settings/team")
    assert response.status_code == 200
    data = response.json()
    assert "members" in data


def test_settings_usage():
    response = client.get("/api/settings/usage")
    assert response.status_code == 200


def test_explorer_mock_search():
    payload = {
        "query": "restaurantes",
        "location": "San Salvador, El Salvador",
        "radius_km": 2.0,
        "category": "Gastronomia",
    }
    response = client.post("/api/explorer/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "total" in data
    assert "saved_new" in data
    assert isinstance(data["results"], list)


def test_explorer_invalid_radius():
    payload = {
        "query": "test",
        "location": "San Salvador",
        "radius_km": 0.1,  # below minimum 0.5
    }
    response = client.post("/api/explorer/search", json=payload)
    assert response.status_code == 422


def test_explorer_invalid_coords():
    payload = {
        "query": "test",
        "location": "San Salvador",
        "latitude": 999,  # invalid
        "longitude": -89.2,
    }
    response = client.post("/api/explorer/search", json=payload)
    assert response.status_code == 422
