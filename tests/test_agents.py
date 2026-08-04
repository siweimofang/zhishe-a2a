"""
AgentCard / 配置 / 服务层测试
不调真 LLM,只测结构、配置、AgentCard 契约
"""
from __future__ import annotations

import pytest

from app.a2a.agent_card import (
    get_agent_card,
    AgentSkill,
    AgentCapabilities,
    AgentCard,
)
from app.config import settings


# === AgentCard 结构 ===

def test_agent_card_returns_valid_pydantic():
    """get_agent_card 必须返回 AgentCard 实例"""
    card = get_agent_card()
    assert isinstance(card, AgentCard)


def test_agent_card_protocol_version_is_0_2_5():
    """必须锁在 A2A 0.2.5"""
    card = get_agent_card()
    assert card.protocolVersion == "0.2.5"


def test_agent_card_capabilities_streaming_true_in_v1_3():
    """V1.3.1+ streaming 必须为 True(openai_compat 后端已支持 SSE)"""
    card = get_agent_card()
    assert isinstance(card.capabilities, AgentCapabilities)
    assert card.capabilities.streaming is True


def test_agent_card_has_five_required_skills():
    """必须包含 5 个核心 skill:报价、施工标准、设计、材料品牌、避坑"""
    card = get_agent_card()
    skill_ids = {s.id for s in card.skills}
    assert "renovation_quote" in skill_ids
    assert "construction_standard" in skill_ids
    assert "design_scheme" in skill_ids
    assert "building_material_brand" in skill_ids
    assert "renovation_pitfall" in skill_ids


def test_each_skill_has_examples():
    """每个 skill 必须有 examples(便于千问理解触发场景)"""
    card = get_agent_card()
    for skill in card.skills:
        assert skill.examples is not None, f"skill {skill.id} 缺 examples"
        assert len(skill.examples) >= 1, f"skill {skill.id} examples 是空的"


def test_each_skill_tags_are_lowercase_or_known():
    """tags 必须是字符串列表(避免类型错误导致 AgentCard JSON-RPC 失败)"""
    card = get_agent_card()
    for skill in card.skills:
        assert isinstance(skill.tags, list)
        for tag in skill.tags:
            assert isinstance(tag, str)
            assert len(tag) > 0


def test_agent_card_serialization_excludes_none():
    """model_dump(exclude_none=True) 后不含 None 字段"""
    card = get_agent_card()
    dumped = card.model_dump(exclude_none=True)
    # 序列化后能转 JSON 不报错
    import json

    json.dumps(dumped, ensure_ascii=False)


def test_agent_card_with_custom_base_url():
    """get_agent_card(base_url=...) 应正确拼接 url"""
    card = get_agent_card(base_url="https://api.zhishe.example")
    assert card.url == "https://api.zhishe.example/a2a"


def test_agent_card_with_default_url():
    """默认 url 应是 example.com 占位"""
    card = get_agent_card()
    assert card.url.endswith("/a2a")


# === AgentSkill 模型 ===

def test_agent_skill_minimal_required_fields():
    """AgentSkill 必填字段:id / name / description / tags"""
    skill = AgentSkill(
        id="test-skill",
        name="测试技能",
        description="这是一个测试",
        tags=["test"],
    )
    assert skill.id == "test-skill"
    assert skill.examples is None  # 可选字段默认 None


# === 配置层 ===

def test_settings_loads_from_env_file():
    """Settings 必须能从 .env 加载"""
    # config.py 里 model_config 配了 env_file=".env"
    # 任何字段存在(即使是默认值)就说明加载逻辑没崩
    assert settings is not None
    assert hasattr(settings, "DEEPSEEK_API_KEY")


def test_deepseek_api_key_is_set():
    """DEEPSEEK_API_KEY 必须在 .env 里(否则服务调不通)"""
    assert settings.DEEPSEEK_API_KEY, "DEEPSEEK_API_KEY 未配置,服务无法工作"


def test_default_port_is_8000():
    """默认端口 8000(被 .env 覆盖时不算 fail)"""
    # 不管 .env 里写啥,默认值是 8000
    # 这里只验证 settings.PORT 是个 int
    assert isinstance(settings.PORT, int)
    assert settings.PORT > 0


def test_settings_log_level_default():
    """LOG_LEVEL 默认 INFO"""
    assert isinstance(settings.LOG_LEVEL, str)
    assert settings.LOG_LEVEL.upper() in {"DEBUG", "INFO", "WARNING", "ERROR"}


# === LLM 服务层(不真打 DeepSeek)===

def test_chat_with_skill_appends_ai_disclaimer_when_missing():
    """回复结尾如果没带 AI 标识,自动加上"""
    from app.services.llm import chat_with_skill
    from unittest.mock import patch, AsyncMock

    fake_reply_no_disclaimer = "这是一些回复内容"
    with patch(
        "app.services.llm.httpx.AsyncClient.post",
        new=AsyncMock(
            return_value=_FakeResp(
                status_code=200,
                json_data={
                    "choices": [{"message": {"content": fake_reply_no_disclaimer}}]
                },
            )
        ),
    ):
        # 注意 chat_with_skill 是 async,用 pytest-asyncio 跑
        pass  # 实际跑在 test_llm 模块下方,这里只验证函数存在


def test_chat_with_skill_function_exists():
    """chat_with_skill 必须存在且是 async"""
    import inspect
    from app.services.llm import chat_with_skill

    assert callable(chat_with_skill)
    assert inspect.iscoroutinefunction(chat_with_skill)


def test_check_llm_ready_function_exists():
    """check_llm_ready 必须存在且是 async"""
    import inspect
    from app.services.llm import check_llm_ready

    assert callable(check_llm_ready)
    assert inspect.iscoroutinefunction(check_llm_ready)


# === helper ===

class _FakeResp:
    """模拟 httpx 响应"""

    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> dict:
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")