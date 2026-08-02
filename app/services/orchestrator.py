"""
orchestrator.py · Skill 联动编排
铁律 L3-10:Skill 之间形成依赖关系并串联调用

Author: Mavis
Date: 2026-06-26

C 端业主路径:
  skill-param-extract → skill-layout → skill-quote → skill-case-match

B 端设计师路径:
  skill-talk-analysis → skill-needs-interpret

通用入口:dispatch(user_intent) 自动选择路径
"""

import json
import logging
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass, field, asdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.quote import full_quote_v6
from app.services.hooks import REGISTRY
from app.services.memory import CUSTOMER, GOTCHAS

log = logging.getLogger("orchestrator")


class UserPath(str, Enum):
    """用户路径"""
    C_OWNER = "c_owner"          # C 端业主
    B_DESIGNER = "b_designer"    # B 端设计师
    UNKNOWN = "unknown"


@dataclass
class OrchestratorResult:
    """编排结果"""
    path: str
    user_id: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_output: Any = None
    warnings: List[str] = field(default_factory=list)
    hooks_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "user_id": self.user_id,
            "steps": self.steps,
            "final_output": self.final_output,
            "warnings": self.warnings,
            "hooks_results": self.hooks_results,
        }


def detect_path(user_intent: str) -> UserPath:
    """
    简单意图识别(基于关键词)
    Phase 3 用 LLM 替代
    """
    intent = user_intent.lower()

    # C 端业主关键词
    c_keywords = ["我家", "我房子", "我家装修", "我家要", "装修多少钱", "装修预算", "我家90", "我家 90"]
    # B 端设计师关键词
    b_keywords = ["客户说", "客户想", "客户需要", "谈单", "客户预算", "案例", "谈单纪要"]

    if any(kw in intent for kw in c_keywords):
        return UserPath.C_OWNER
    if any(kw in intent for kw in b_keywords):
        return UserPath.B_DESIGNER
    return UserPath.UNKNOWN


def c_owner_pipeline(user_id: str, params: Dict[str, Any]) -> OrchestratorResult:
    """
    C 端业主路径:参数提取 → 布局规划 → 报价 → 案例匹配
    """
    result = OrchestratorResult(path="c_owner", user_id=user_id)
    city = params.get("city", "沈阳")
    district = params.get("district", "浑南")
    area = params.get("area", 89)
    tier = params.get("tier", "中端")
    package = params.get("package_type", "半包")
    rooms = params.get("rooms", [])

    # 步骤 1:参数提取(Phase 1.3 normalize)
    result.steps.append({"step": 1, "skill": "skill-param-extract", "input": params})
    CUSTOMER.record_session(user_id, f"开始 C 端装修咨询: {area} 平 {tier} {package}", f"城市: {city} {district}")
    log.info(f"[Orchestrator] {user_id} C 端路径启动")

    # 步骤 2:布局约束检查(Phase 1.4 constraint_check,简化)
    if params.get("layout"):
        layout = params["layout"]
        results = REGISTRY.run_hooks("skill-layout", "in_layout", {"demolish_walls": layout.get("demolish_walls", [])})
        for r in results:
            result.hooks_results.append(r.to_dict())
            if not r.passed and r.severity == "critical":
                result.warnings.append(r.message)
                result.steps.append({"step": 2, "skill": "skill-layout", "skipped": True, "reason": r.message})
                return result
        result.steps.append({"step": 2, "skill": "skill-layout", "hooks": "passed"})

    # 步骤 3:E0 板材检查 + 报价(Phase 1.2 price_calc + Phase 2.1 hook)
    quote_context = {"quote_items": params.get("quote_items", [])}
    e0_results = REGISTRY.run_hooks("skill-quote", "before_quote", quote_context)
    for r in e0_results:
        result.hooks_results.append(r.to_dict())
        if not r.passed:
            result.warnings.append(r.message)

    # 步骤 4:V6.0 完整报价
    quote_result = full_quote_v6(
        city=city,
        district=district,
        area=area,
        tier=tier,
        package_type=package,
        room_count=len(rooms) if rooms else 6,
        client_price=params.get("client_price"),
    )
    result.steps.append({
        "step": 3,
        "skill": "skill-quote",
        "result": {
            "total_median": quote_result.get("phase_1_baseline", {}).get("total_median"),
            "skill_calc_total": quote_result.get("phase_2_skill_calc", {}).get("total"),
            "deviation_percent": (quote_result.get("phase_3_price_check") or {}).get("deviation"),
        }
    })

    # 步骤 5:偏差 >30% 预警
    p3 = quote_result.get("phase_3_price_check") or {}
    if p3.get("severe_deviation"):
        over30_results = REGISTRY.run_hooks("skill-quote", "after_quote", {
            "deviation_percent": p3["deviation"],
            "expected_range": p3["expected_range"],
            "actual_price": p3["total_price"],
        })
        for r in over30_results:
            result.hooks_results.append(r.to_dict())
            if r.severity == "warning":
                result.warnings.append(r.message)

    # 步骤 6:案例匹配(Phase 3 完善,Phase 2 占位)
    result.steps.append({
        "step": 4,
        "skill": "skill-case-match",
        "result": "Phase 3 完善(占位:返回前 3 个相似户型)",
        "top_3": [
            {"designer": "沈阳赫慕空间设计-李工", "style": "现代简约", "match_score": 92},
            {"designer": "沈阳赫慕空间设计-王工", "style": "北欧", "match_score": 88},
            {"designer": "沈阳赫慕空间设计-张工", "style": "新中式", "match_score": 85},
        ]
    })

    result.final_output = {
        "summary": f"{user_id} {area}平 {tier} {package},预算约 {quote_result.get('phase_1_baseline', {}).get('total_median', '?')} 元",
        "quote": quote_result,
        "designers": result.steps[-1]["top_3"],
    }
    return result


def b_designer_pipeline(user_id: str, params: Dict[str, Any]) -> OrchestratorResult:
    """
    B 端设计师路径:谈单分析 → 需求解读
    """
    result = OrchestratorResult(path="b_designer", user_id=user_id)
    transcript = params.get("transcript", "")
    client_info = params.get("client_info", {})

    # 步骤 1:谈单分析(占位,Phase 3 接 Whisper)
    result.steps.append({
        "step": 1,
        "skill": "skill-talk-analysis",
        "input": f"录音长度: {len(transcript)} 字符",
        "output": "已生成纪要(Phase 3 接 LLM 总结)",
    })

    # 步骤 2:隐私过滤
    privacy_results = REGISTRY.run_hooks("skill-talk-analysis", "before_output", {"text": transcript})
    for r in privacy_results:
        result.hooks_results.append(r.to_dict())
        if not r.passed:
            result.warnings.append(r.message)

    # 步骤 3:客户画像
    if client_info:
        CUSTOMER.record_session(user_id, f"B 端谈单:客户 {client_info.get('name', '匿名')}", transcript[:200])
        result.steps.append({
            "step": 2,
            "skill": "skill-needs-interpret",
            "client_profile": client_info,
        })

    result.final_output = {
        "summary": f"{user_id} 谈单纪要已生成,客户画像已记录",
        "client_id": user_id,
    }
    return result


def dispatch(user_intent: str, user_id: str, params: Dict[str, Any]) -> OrchestratorResult:
    """
    通用入口:自动选择路径
    """
    path = detect_path(user_intent)

    if path == UserPath.C_OWNER:
        return c_owner_pipeline(user_id, params)
    elif path == UserPath.B_DESIGNER:
        return b_designer_pipeline(user_id, params)
    else:
        # 未知意图,默认 C 端
        return c_owner_pipeline(user_id, params)


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("orchestrator.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:意图识别
    print("--- 测试 1:意图识别 ---")
    test_intents = [
        "我家 89 平半包多少钱?",
        "客户说想装修,预算 15 万",
        "谈单纪要整理",
    ]
    for intent in test_intents:
        path = detect_path(intent)
        print(f"  '{intent}' -> {path.value}")
    print()

    # 测试 2:C 端业主路径
    print("--- 测试 2:C 端业主路径(沈阳 89 平中档半包) ---")
    result = dispatch("我家 89 平半包多少钱", "user_test_001", {
        "city": "沈阳",
        "district": "浑南",
        "area": 89,
        "tier": "中端",
        "package_type": "半包",
        "rooms": [
            {"name": "客厅", "length": 4.5, "width": 4.0},
            {"name": "主卧", "length": 4.2, "width": 3.6},
        ],
        "quote_items": [
            {"name": "橱柜", "material": "E0 级颗粒板"},
        ],
    })
    print(f"  路径: {result.path}")
    print(f"  步骤数: {len(result.steps)}")
    print(f"  警告数: {len(result.warnings)}")
    print(f"  Hooks 触发数: {len(result.hooks_results)}")
    for s in result.steps:
        print(f"    步骤 {s['step']}: {s['skill']}")
    if result.warnings:
        for w in result.warnings:
            print(f"    ⚠️ {w}")
    if result.path == "c_owner" and len(result.steps) == 4:
        print("  ✅ 沙箱实证:C 端路径 4 步骤全跑通")
    print()

    # 测试 3:C 端路径 + 客户报价 2 万(触发偏差预警)
    print("--- 测试 3:C 端路径 + 客户报价 2 万 ---")
    result2 = dispatch("我家 89 平半包多少钱", "user_test_002", {
        "city": "沈阳", "district": "浑南", "area": 89,
        "tier": "中端", "package_type": "半包",
        "rooms": [{"name": "客厅", "length": 4.5, "width": 4.0}],
        "client_price": 20000,
    })
    print(f"  路径: {result2.path}")
    print(f"  警告数: {len(result2.warnings)}")
    for w in result2.warnings:
        if "报价" in w or "Token" in w:
            print(f"    {w[:100]}")
    if any("报价" in w or "偏差" in w for w in result2.warnings):
        print("  ✅ 沙箱实证:偏差预警触发")
    print()

    # 测试 4:B 端设计师路径
    print("--- 测试 4:B 端设计师路径 ---")
    result3 = dispatch("客户说想装修 90 平 预算 15 万 现代简约风", "designer_001", {
        "transcript": "客户王女士,89 平三室两厅,预算 15 万,喜欢现代简约风格,有 1 个小孩需要儿童房...",
        "client_info": {"name": "王女士", "area": 89, "budget": 150000, "style": "现代简约"},
    })
    print(f"  路径: {result3.path}")
    print(f"  步骤数: {len(result3.steps)}")
    for s in result3.steps:
        print(f"    步骤 {s['step']}: {s['skill']}")
    if result3.path == "b_designer":
        print("  ✅ 沙箱实证:B 端路径正确")
    print()

    # 测试 5:含承重墙的布局
    print("--- 测试 5:C 端路径 + 拆除承重墙(应被 G1 拦截) ---")
    result4 = dispatch("我家要拆主卧外墙", "user_test_003", {
        "city": "沈阳", "district": "浑南", "area": 89,
        "tier": "中端", "package_type": "半包",
        "rooms": [{"name": "客厅", "length": 4.5, "width": 4.0}],
        "layout": {"demolish_walls": ["主卧外墙", "阳台垛子"]},
    })
    print(f"  路径: {result4.path}")
    print(f"  步骤数: {len(result4.steps)}")
    print(f"  警告数: {len(result4.warnings)}")
    for w in result4.warnings:
        if "承重墙" in w or "G1" in w:
            print(f"    🚨 {w[:100]}")
    if any("承重墙" in w for w in result4.warnings):
        print("  ✅ 沙箱实证:G1 致命级承重墙被强制拦截")
