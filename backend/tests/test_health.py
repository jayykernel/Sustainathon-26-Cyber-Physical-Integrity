"""Health check test for FastAPI app."""

import pytest
from fastapi.testclient import TestClient

from physiguard.api.app import create_app


def test_health_endpoint(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that /api/health returns 200 with expected keys."""
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "config_hash" in data
    assert "version" in data
    assert "thresholds_loaded" in data
    assert data["config_hash"] in capsys.readouterr().out
