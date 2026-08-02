"""
OpenAI-compatible 端点测试 (2026-06-13, V2.0 接管路径)
"""
from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


def test_openai_chat_completions_no_auth_returns_401():
    """没带鉴权应该 401"""
    from app.main import app
    client = TestClient(app)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


def test_openai_chat_completions_success():
    """带鉴权 + 正常消息 → 200 + OpenAI 格式响应"""
    from app.main import app
    from tests.conftest import AUTH_HEADER

    fake_reply = "沈阳 90 平半包参考 4-5 万。(以上内容由 AI 生成,仅供参考)"

    with patch(
        "app.api.openai_compat.chat_with_skill",
        new=AsyncMock(return_value=fake_reply),
    ):
        client = TestClient(app, headers=AUTH_HEADER)
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "zhishe-a2a",
                "messages": [{"role": "user", "content": "沈阳 90 平半包大概多少钱?"}],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        # OpenAI 格式校验
        assert body["object"] == "chat.completion"
        assert body["model"] == "zhishe-a2a"
        assert len(body["choices"]) == 1
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert fake_reply in body["choices"][0]["message"]["content"]
        assert body["choices"][0]["finish_reason"] == "stop"
        # usage 字段
        assert "usage" in body
        assert "prompt_tokens" in body["usage"]
        assert "completion_tokens" in body["usage"]


def test_openai_chat_completions_empty_messages_400():
    """空 messages 应该 400"""
    from app.main import app
    from tests.conftest import AUTH_HEADER

    client = TestClient(app, headers=AUTH_HEADER)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": []},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert body["error"]["type"] == "invalid_request_error"


def test_openai_chat_completions_no_user_message_400():
    """messages 里没有 user role 应该 400"""
    from app.main import app
    from tests.conftest import AUTH_HEADER

    client = TestClient(app, headers=AUTH_HEADER)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "system", "content": "你是一个助手"}]},
    )
    assert resp.status_code == 400


def test_openai_chat_completions_multimodal_content():
    """content 是 list of parts (OpenAI 多模态格式) → 正确提取 text"""
    from app.main import app
    from tests.conftest import AUTH_HEADER

    fake_reply = "好的,装修报价大约 4-5 万。(以上内容由 AI 生成,仅供参考)"

    with patch(
        "app.api.openai_compat.chat_with_skill",
        new=AsyncMock(return_value=fake_reply),
    ) as mock_chat:
        client = TestClient(app, headers=AUTH_HEADER)
        resp = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "装修"},
                            {"type": "text", "text": "大概多少钱?"},
                        ],
                    }
                ],
            },
        )
        assert resp.status_code == 200
        # 应该把 "装修 大概多少钱?" 传给 chat_with_skill
        called_text = mock_chat.call_args[0][0]
        assert "装修" in called_text
        assert "大概多少钱" in called_text


def test_openai_chat_completions_invalid_json_400():
    """body 不是合法 JSON 应该 400"""
    from app.main import app
    from tests.conftest import AUTH_HEADER

    client = TestClient(app, headers=AUTH_HEADER)
    resp = client.post(
        "/v1/chat/completions",
        content="not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
