"""
共享 pytest fixtures
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_send_payload() -> dict:
    """最小可用的 A2A message/send 请求体"""
    return {
        "jsonrpc": "2.0",
        "id": "test-001",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "沈阳 90 平半包大概多少?"}],
            }
        },
    }