import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_login_missing_password():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"email": "a@b.com"})
    assert response.status_code == 422


def test_login_missing_email():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"password": "secret"})
    assert response.status_code == 422


def test_login_empty_body():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={})
    assert response.status_code == 422


def test_register_missing_email():
    client = TestClient(app)
    response = client.post("/api/auth/register", json={"password": "secret123"})
    assert response.status_code == 422


def test_register_missing_password():
    client = TestClient(app)
    response = client.post("/api/auth/register", json={"email": "a@b.com"})
    assert response.status_code == 422


def test_me_returns_user(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "email" in data
    assert "workspace_id" in data
