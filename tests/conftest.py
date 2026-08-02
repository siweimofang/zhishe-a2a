"""
共享 pytest fixtures
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings


# 鉴权头(.env 配了 A2A_API_KEY 时必须带,test_protocol/test_streaming 用)
AUTH_HEADER = (
    {"Authorization": f"Bearer {settings.A2A_API_KEY}"}
    if settings.A2A_API_KEY
    else {}
)


@pytest.fixture
def client() -> TestClient:
    """默认带鉴权头的 client(.env 配 A2A_API_KEY 时必须)"""
    return TestClient(app, headers=AUTH_HEADER)


@pytest.fixture
def unauth_client() -> TestClient:
    """不带鉴权头的 client(专门测鉴权失败场景)"""
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