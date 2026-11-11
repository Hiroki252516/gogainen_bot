import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core import admin_auth
from app.core.config import get_settings
from app.main import app


def test_all_admin_routes_reject_anonymous_requests():
    client = TestClient(app)
    paths = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not admin_auth._is_admin_path(path) or path.startswith("/api/admin/auth/"):
            continue
        path = path.replace("{participant_id}", "missing").replace("{name}", "attempts")
        for method in route.methods - {"OPTIONS", "HEAD"}:
            result = client.request(method, path, json={})
            assert result.status_code == 401, (method, path, result.text)
            assert "no-store" in result.headers.get("cache-control", "") or "recalculate" in path
            paths.append(path)
    assert len(paths) >= 25


def test_login_cookie_csv_logout_and_revocation():
    client = TestClient(app)
    assert client.post("/api/admin/auth/login", json={"password": "wrong"}).status_code == 401
    assert not client.cookies.get(admin_auth.COOKIE_NAME)
    response = client.post("/api/admin/auth/login", json={"password": "abc"})
    assert response.json() == {"authenticated": True}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
    assert response.cookies.get(admin_auth.COOKIE_NAME) != "abc"
    token = client.cookies.get(admin_auth.COOKIE_NAME)
    assert client.get("/api/admin/participants").status_code == 200
    assert client.get("/api/admin/logs/overview.csv").status_code == 200
    assert client.get("/api/admin/identity-mappings.csv").status_code == 200
    assert client.get("/api/admin/research-code-mappings.csv").status_code == 200
    logout = client.post("/api/admin/auth/logout")
    assert logout.status_code == 200
    assert "Secure" not in logout.headers["set-cookie"]
    assert "Max-Age=0" in logout.headers["set-cookie"]
    client.cookies.set(admin_auth.COOKIE_NAME, token)
    assert client.get("/api/admin/participants").status_code == 401


def test_forged_expired_and_rotated_sessions_are_rejected(monkeypatch):
    client = TestClient(app)
    client.cookies.set(admin_auth.COOKIE_NAME, "forged")
    assert client.get("/api/admin/participants").status_code == 401
    client.cookies.clear()
    client.post("/api/admin/auth/login", json={"password": "abc"})
    first = client.cookies.get(admin_auth.COOKIE_NAME)
    client.post("/api/admin/auth/login", json={"password": "abc"})
    token = client.cookies.get(admin_auth.COOKIE_NAME)
    assert first != token and first not in admin_auth._sessions
    monkeypatch.setitem(admin_auth._sessions, token, admin_auth.time.monotonic() - 1)
    assert client.get("/api/admin/participants").status_code == 401


@pytest.mark.parametrize("payload", [{}, {"password": 123}, {"password": ""}, {"password": "x" * 257}, {"password": "abc", "extra": "do-not-echo"}])
def test_invalid_password_payload_is_not_echoed(payload):
    response = TestClient(app).post("/api/admin/auth/login", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "パスワードの入力形式を確認してください。"}


def test_cross_origin_writes_rejected_and_public_flow_unchanged():
    client = TestClient(app)
    assert client.post("/api/admin/auth/login", json={"password": "abc"}, headers={"Origin": "http://other.invalid"}).status_code == 403
    assert client.post("/api/admin/auth/login", json={"password": "abc"}).status_code == 200
    assert client.put("/api/admin/option-order", json={"mode": "randomized"}, headers={"Origin": "http://other.invalid"}).status_code == 403
    assert client.get("/api/admin/option-order").status_code == 200
    anonymous = TestClient(app)
    assert anonymous.get("/api/health").status_code == 200
    assert anonymous.post("/api/registrations", json={}).status_code != 401


def test_configured_password_and_https_cookie(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_password", SecretStr("changed-password"))
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/api/admin/auth/login", json={"password": "abc"}).status_code == 401
    response = client.post("/api/admin/auth/login", json={"password": "changed-password"})
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    assert client.get("/api/admin/participants").status_code == 200
    token = client.cookies.get(admin_auth.COOKIE_NAME)
    logout = client.post("/api/admin/auth/logout")
    assert logout.status_code == 200
    assert "Secure" in logout.headers["set-cookie"]
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert client.get("/api/admin/participants").status_code == 401
    client.cookies.set(admin_auth.COOKIE_NAME, token, path="/api")
    assert client.get("/api/admin/participants").status_code == 401


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_configured_ui_and_existing_loopback_alias_can_login(origin):
    response = TestClient(app).post("/api/admin/auth/login", json={"password": "abc"}, headers={"Origin": origin})
    assert response.status_code == 200
