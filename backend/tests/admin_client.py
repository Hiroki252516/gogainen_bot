"""Existing experiment tests exercise researcher APIs as an authenticated researcher."""

from fastapi.testclient import TestClient
from app.core.config import get_settings


class AuthenticatedTestClient(TestClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        response = self.post("/api/admin/auth/login", json={"password": get_settings().admin_password.get_secret_value()})
        assert response.status_code == 200, response.text
