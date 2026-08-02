"""
hook_runner.py · Hook 编排中间件
铁律 L3-9:Hook 在 Skill 调用前后自动跑

Author: Mavis
Date: 2026-06-26

在 openai_compat.py 路由中插入:
请求前:hook-budget-fuse(token 检查) + hook-privacy-filter(用户输入)
响应后:hook-over30-warn(报价偏差)
"""

import logging
from typing import Dict, Any, List, Optional, AsyncIterator

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.hooks import REGISTRY, HookResult
from app.services.orchestrator import dispatch as orchestrator_dispatch, OrchestratorResult

log = logging.getLogger("hook_runner")


async def pre_request_hooks(
    request_body: Dict[str, Any],
    token_count: int = 0,
    max_tokens: int = 8000,
) -> List[HookResult]:
    """
    请求前 Hook:
    - hook-budget-fuse(token 检查)
    - hook-privacy-filter(用户输入)

    Args:
        request_body: OpenAI 格式的请求体
        token_count: 当前 token 数
        max_tokens: 上下文 token 上限

    Returns:
        Hook 结果列表
    """
    results = []

    # 1. Token 熔断
    token_results = REGISTRY.run_hooks("skill-quote", "before_quote", {
        "token_count": token_count,
        "max_tokens": max_tokens,
    })
    results.extend(token_results)

    # 2. 隐私过滤(用户消息)
    messages = request_body.get("messages", [])
    if messages:
        last_msg = messages[-1].get("content", "")
        if isinstance(last_msg, str):
            privacy_results = REGISTRY.run_hooks("skill-talk-analysis", "before_output", {
                "text": last_msg,
            })
            results.extend(privacy_results)

    for r in results:
        log.info(f"[PreHook] {r.severity}: passed={r.passed} - {r.message}")

    return results


async def post_response_hooks(
    response_text: str,
    user_intent: str = "",
) -> List[HookResult]:
    """
    响应后 Hook:
    - hook-privacy-filter(响应文本)
    - hook-over30-warn(报价偏差,如有)
    """
    results = []

    privacy_results = REGISTRY.run_hooks("skill-talk-analysis", "before_output", {
        "text": response_text,
    })
    results.extend(privacy_results)

    for r in results:
        log.info(f"[PostHook] {r.severity}: passed={r.passed} - {r.message}")

    return results


def extract_intent_and_params(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从 OpenAI messages 提取用户意图和参数
    简化版(Phase 3 用 LLM 优化)
    """
    if not messages:
        return {"user_intent": "", "user_id": "anonymous", "params": {}}

    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                last_user_msg = content
                break

    # 简化提取(Phase 3 用 LLM 替代)
    import re
    params = {}
    area_match = re.search(r"(\d+)\s*平", last_user_msg)
    if area_match:
        params["area"] = int(area_match.group(1))
    city_match = re.search(r"(沈阳|北京|上海|广州|深圳|杭州|成都|南京|武汉|西安|大连|长春|哈尔滨)", last_user_msg)
    if city_match:
        params["city"] = city_match.group(1)
    if "半包" in last_user_msg:
        params["package_type"] = "半包"
    elif "大包" in last_user_msg:
        params["package_type"] = "大包"
    elif "全案" in last_user_msg:
        params["package_type"] = "全案"
    if "中档" in last_user_msg or "中端" in last_user_msg:
        params["tier"] = "中端"
    elif "经济" in last_user_msg:
        params["tier"] = "经济"
    elif "高端" in last_user_msg or "豪华" in last_user_msg:
        params["tier"] = "高端"

    return {
        "user_intent": last_user_msg,
        "user_id": "anonymous",
        "params": params,
    }


async def run_orchestrator_if_needed(
    user_intent: str,
    user_id: str,
    params: Dict[str, Any],
) -> Optional[OrchestratorResult]:
    """
    如果意图是装修咨询,运行 orchestrator
    否则返回 None(走原有 LLM 流程)
    """
    keywords = ["多少钱", "半包", "大包", "全案", "装修预算", "装修多少钱", "报价", "我家", "客户"]
    if not any(kw in user_intent for kw in keywords):
        return None

    log.info(f"[Orchestrator] 触发: {user_intent[:50]}...")
    result = orchestrator_dispatch(user_intent, user_id, params)
    log.info(f"[Orchestrator] 路径: {result.path}, 步骤: {len(result.steps)}, 警告: {len(result.warnings)}")
    return result


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    import asyncio

    print("=" * 60)
    print("hook_runner.py 沙箱实证")
    print("=" * 60)
    print()

    async def run_tests():
        # 测试 1:请求前 hooks
        print("--- 测试 1:请求前 hooks(正常 token) ---")
        results = await pre_request_hooks(
            {"messages": [{"role": "user", "content": "我家 89 平半包多少钱?"}]},
            token_count=1000, max_tokens=8000,
        )
        for r in results:
            print(f"  [{r.severity}] passed={r.passed}: {r.message[:80]}")
        if all(r.passed for r in results):
            print("  ✅ 沙箱实证:正常 token 通过所有 hook")
        print()

        # 测试 2:Token 超限
        print("--- 测试 2:Token 超限(token 7800/8000) ---")
        results = await pre_request_hooks(
            {"messages": []}, token_count=7800, max_tokens=8000,
        )
        for r in results:
            print(f"  [{r.severity}] passed={r.passed}: {r.message[:80]}")
        if any("Token" in r.message for r in results):
            print("  ✅ 沙箱实证:Token 熔断触发")
        print()

        # 测试 3:用户输入含隐私
        print("--- 测试 3:用户输入含手机号 ---")
        results = await pre_request_hooks(
            {"messages": [{"role": "user", "content": "客户王女士 13800138000 想装修 89 平"}]},
        )
        for r in results:
            print(f"  [{r.severity}] passed={r.passed}: {r.message[:80]}")
        if any("手机号" in r.message for r in results):
            print("  ✅ 沙箱实证:隐私过滤触发")
        print()

        # 测试 4:响应后 hooks
        print("--- 测试 4:响应后 hooks(响应含身份证) ---")
        results = await post_response_hooks(
            "客户身份证 210311198010270014 想装修",
        )
        for r in results:
            print(f"  [{r.severity}] passed={r.passed}: {r.message[:80]}")
        if any("身份" in r.message for r in results):
            print("  ✅ 沙箱实证:响应隐私拦截")
        print()

        # 测试 5:参数提取
        print("--- 测试 5:参数提取 ---")
        info = extract_intent_and_params([
            {"role": "user", "content": "我家沈阳 89 平半包大概多少钱?"},
        ])
        print(f"  提取: {info}")
        if info["params"].get("city") == "沈阳" and info["params"].get("area") == 89:
            print("  ✅ 沙箱实证:参数提取成功")
        print()

        # 测试 6:触发 orchestrator
        print("--- 测试 6:触发 orchestrator ---")
        result = await run_orchestrator_if_needed(
            user_intent="我家沈阳 89 平半包",
            user_id="user_001",
            params={"city": "沈阳", "district": "浑南", "area": 89, "tier": "中端", "package_type": "半包"},
        )
        if result:
            print(f"  路径: {result.path}, 步骤: {len(result.steps)}")
            print("  ✅ 沙箱实证:orchestrator 触发成功")
        print()

        # 测试 7:不触发 orchestrator
        print("--- 测试 7:不触发 orchestrator(闲聊) ---")
        result = await run_orchestrator_if_needed(
            user_intent="你好,今天天气怎么样?",
            user_id="user_001",
            params={},
        )
        if result is None:
            print("  ✅ 沙箱实证:闲聊不触发 orchestrator")

    asyncio.run(run_tests())
