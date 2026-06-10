"""
A2A 0.2.5 协议层测试
覆盖端点:/a2a/message/send、鉴权、错误响应、LLM 调用 mock
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from app.main import app


# === fixtures ===

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


# === 健康检查 & 元信息 ===

def test_root_returns_service_metadata(client: TestClient):
    """根路径返回服务元信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "zhishe-ai-renovation"
    assert body["protocol"] == "A2A 0.2.5"
    assert "endpoints" in body


def test_agent_card_endpoint(client: TestClient):
    """AgentCard 端点返回符合 A2A 规范的 JSON"""
    resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["protocolVersion"] == "0.2.5"
    assert body["name"] == "知设AI装修顾问"
    assert isinstance(body["skills"], list)
    assert len(body["skills"]) >= 3
    # 每个 skill 必须有 id/name/description/tags
    for skill in body["skills"]:
        assert "id" in skill
        assert "name" in skill
        assert "description" in skill
        assert "tags" in skill
        assert isinstance(skill["tags"], list)


# === message/send 协议层 ===

def test_message_send_success(client: TestClient, sample_send_payload: dict):
    """正常 message/send 请求应返回 200 + JSON-RPC result"""
    fake_reply = "90 平半包参考 5-7 万。(以上内容由 AI 生成,仅供参考)"
    with patch(
        "app.a2a.server.chat_with_skill",
        new=AsyncMock(return_value=fake_reply),
    ):
        resp = client.post("/a2a/message/send", json=sample_send_payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "test-001"
    assert "result" in body, f"expected result, got {body}"
    task = body["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "completed"
    # A2A 0.2.5 必须用 kind=text(不是 type=text,这是昨天修过的 bug)
    parts = task["artifacts"][0]["parts"]
    assert parts[0]["kind"] == "text"
    assert "AI 生成" in parts[0]["text"]


def test_message_send_method_not_found(client: TestClient):
    """不支持的方法返回 JSON-RPC -32601 错误"""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-002",
        "method": "message/unknown",
        "params": {"message": {"role": "user", "parts": []}},
    }
    resp = client.post("/a2a/message/send", json=payload)
    assert resp.status_code == 200  # JSON-RPC 错误也用 HTTP 200
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32601


def test_message_send_streaming_not_supported(client: TestClient):
    """message/stream 在 V1.0 返回 -32601"""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-003",
        "method": "message/stream",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "hi"}],
            }
        },
    }
    resp = client.post("/a2a/message/send", json=payload)
    body = resp.json()
    assert body["error"]["code"] == -32601
    assert "Streaming" in body["error"]["message"]


def test_message_send_empty_parts_returns_error(client: TestClient):
    """空 parts 返回 -32602"""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-004",
        "method": "message/send",
        "params": {"message": {"role": "user", "parts": []}},
    }
    resp = client.post("/a2a/message/send", json=payload)
    body = resp.json()
    assert body["error"]["code"] == -32602


def test_message_send_invalid_json_returns_parse_error(client: TestClient):
    """非法 JSON 返回 -32700 parse error"""
    resp = client.post(
        "/a2a/message/send",
        content="{invalid json}",
        headers={"Content-Type": "application/json"},
    )
    body = resp.json()
    assert body["error"]["code"] == -32700


def test_message_send_concatenates_multiple_text_parts(client: TestClient):
    """多 text part 应拼成一个 user_text"""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-005",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {"kind": "text", "text": "沈阳 "},
                    {"kind": "text", "text": "90 平"},
                ],
            }
        },
    }
    captured = {}

    async def fake_chat(text: str) -> str:
        captured["text"] = text
        return "ok"

    with patch("app.a2a.server.chat_with_skill", new=AsyncMock(side_effect=fake_chat)):
        resp = client.post("/a2a/message/send", json=payload)

    assert resp.status_code == 200
    assert captured["text"] == "沈阳 90 平"


def test_message_send_llm_error_returns_internal_error(client: TestClient, sample_send_payload: dict):
    """LLM 抛异常时返回 -32603"""
    with patch(
        "app.a2a.server.chat_with_skill",
        new=AsyncMock(side_effect=RuntimeError("DeepSeek 502")),
    ):
        resp = client.post("/a2a/message/send", json=sample_send_payload)

    body = resp.json()
    assert body["error"]["code"] == -32603
    assert "DeepSeek 502" in body["error"]["message"]


# === 鉴权 ===

def test_no_api_key_required_when_setting_empty(client: TestClient, sample_send_payload: dict):
    """A2A_API_KEY 为空时不强制鉴权(本地联调模式)"""
    from app.config import settings

    if settings.A2A_API_KEY:
        pytest.skip("A2A_API_KEY 已配置,跳过'不强制鉴权'测试")

    with patch(
        "app.a2a.server.chat_with_skill",
        new=AsyncMock(return_value="ok"),
    ):
        resp = client.post("/a2a/message/send", json=sample_send_payload)
    assert resp.status_code == 200
    assert "result" in resp.json()


def test_api_key_required_when_setting_configured(client: TestClient, sample_send_payload: dict):
    """A2A_API_KEY 配置后,缺少/错误 key 返回 401"""
    with patch("app.a2a.server.settings") as mock_settings:
        mock_settings.A2A_API_KEY = "test-secret-key-123"

        resp_no_header = client.post("/a2a/message/send", json=sample_send_payload)
        assert resp_no_header.status_code == 401

        resp_wrong_key = client.post(
            "/a2a/message/send",
            json=sample_send_payload,
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp_wrong_key.status_code == 401

        resp_correct = client.post(
            "/a2a/message/send",
            json=sample_send_payload,
            headers={"X-API-Key": "test-secret-key-123"},
        )
        assert resp_correct.status_code == 200