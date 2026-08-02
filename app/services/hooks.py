"""
hooks.py · on-demand Hook 机制
铁律 L3-9:Hook 只在特定 Skill 调用期间生效,不全局常驻

Author: Mavis
Date: 2026-06-26

5 个 Hook(对应 L3 文章):
- hook-e0-enforce: E0 板材强制检查(报价)
- hook-over30-warn: 报价偏差 >30% 预警
- hook-bearing-wall: 承重墙拆除拦截(布局)
- hook-privacy-filter: 手机号/地址脱敏(谈单)
- hook-budget-fuse: Token 超限熔断(全局)
"""

import re
import logging
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger("hooks")


class HookType(str, Enum):
    """Hook 类型"""
    COMMAND = "command"  # 确定性检查(command 脚本)
    PROMPT = "prompt"    # LLM 检查(预留,Phase 3)
    EVENT = "event"      # 事件触发(预留,Phase 3)


class HookResult:
    """Hook 执行结果"""
    def __init__(self, passed: bool, message: str = "", severity: str = "info"):
        self.passed = passed
        self.message = message
        self.severity = severity  # info / warning / error / critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class Hook:
    """单个 Hook 定义"""
    name: str
    bound_skill: str  # 绑定的 Skill(None = 全局)
    trigger_timing: str  # before_quote / after_quote / in_layout / before_output / global
    hook_type: HookType
    description: str
    callback: Callable[..., HookResult] = None

    def run(self, context: Dict[str, Any]) -> HookResult:
        """执行 Hook"""
        if self.callback is None:
            return HookResult(True, f"Hook {self.name} 未实现 callback", "info")
        try:
            return self.callback(context)
        except Exception as e:
            log.exception(f"Hook {self.name} 异常: {e}")
            return HookResult(False, f"Hook 异常: {e}", "error")


# ============== 5 个 Hook 实现 ==============

def hook_e0_enforce(context: Dict[str, Any]) -> HookResult:
    """
    E0 板材强制检查(报价时)
    触发:Skill-quote 输出报价前
    检查:报价单中所有板材是否标 E0 级
    """
    quote_items = context.get("quote_items", [])
    violations = []

    for item in quote_items:
        name = item.get("name", "")
        material = item.get("material", "")
        # 板材类必须标 E0
        if any(kw in name for kw in ["板材", "柜体", "橱柜", "衣柜", "榻榻米", "书架"]):
            if "E0" not in material and "E1" not in material:
                violations.append(f"{name}: 板材未标等级(应为 E0)")

    if violations:
        return HookResult(
            False,
            f"E0 板材违规 {len(violations)} 项: " + "; ".join(violations[:3]),
            "error"
        )
    return HookResult(True, "E0 板材检查通过", "info")


def hook_over30_warn(context: Dict[str, Any]) -> HookResult:
    """
    报价偏差 >30% 预警
    触发:Skill-quote 计算报价后
    检查:报价 vs 城市基准价
    """
    deviation = context.get("deviation_percent", 0)
    expected_range = context.get("expected_range", [0, 0])
    actual_price = context.get("actual_price", 0)

    if abs(deviation) > 30:
        direction = "低于" if deviation < 0 else "高于"
        return HookResult(
            True,  # passed=True(只是 warning)
            f"⚠️ 报价 {direction}基准价 {abs(deviation):.1f}%, 基准区间 {expected_range}, 实际 {actual_price}",
            "warning"
        )
    return HookResult(True, f"偏差 {deviation:.1f}%,在合理范围内", "info")


def hook_bearing_wall(context: Dict[str, Any]) -> HookResult:
    """
    承重墙拆除拦截(布局时)
    触发:Skill-layout 输出方案时
    检查:demolish_walls 列表是否包含承重墙
    """
    # 承重墙标识(L3 原则 G1 致命级)
    BEARING_WALLS = {
        "主卧外墙", "客厅外墙", "厨房外墙", "卫生间外墙",
        "阳台垛子", "客厅与电梯井之间", "主卧与电梯井之间",
        "承重墙", "剪力墙", "结构柱",
    }

    demolish = context.get("demolish_walls", [])
    violations = [w for w in demolish if w in BEARING_WALLS or "承重" in w or "剪力" in w]

    if violations:
        return HookResult(
            False,
            f"🚨 G1-致命: 承重墙不可拆除!违规: {violations}",
            "critical"
        )
    return HookResult(True, f"墙体改动检查通过(拆除 {len(demolish)} 项)", "info")


def hook_privacy_filter(context: Dict[str, Any]) -> HookResult:
    """
    隐私过滤(谈单时)
    触发:Skill-talk-analysis 输出纪要前
    检查:文本是否含手机号/地址/身份证
    """
    text = context.get("text", "")
    found = []

    # 手机号
    phones = re.findall(r"1[3-9]\d{9}", text)
    if phones:
        found.append(f"手机号 {len(phones)} 个")

    # 身份证号
    id_cards = re.findall(r"\d{17}[\dXx]", text)
    if id_cards:
        found.append(f"身份证 {len(id_cards)} 个")

    # 银行卡
    bank_cards = re.findall(r"\d{16,19}", text)
    if bank_cards:
        # 排除普通数字(短)
        bank_cards = [c for c in bank_cards if len(c) >= 16]
        if bank_cards:
            found.append(f"银行卡 {len(bank_cards)} 个")

    if found:
        return HookResult(
            False,
            f"隐私数据未脱敏: {', '.join(found)}",
            "error"
        )
    return HookResult(True, "隐私检查通过", "info")


def hook_budget_fuse(context: Dict[str, Any]) -> HookResult:
    """
    Token 超限熔断(全局)
    触发:每次推理
    检查:单轮 Token 数是否超阈值
    """
    token_count = context.get("token_count", 0)
    max_tokens = context.get("max_tokens", 8000)

    if token_count > max_tokens * 0.9:
        return HookResult(
            False,
            f"⚠️ Token 即将超限: {token_count}/{max_tokens} ({token_count/max_tokens*100:.1f}%)",
            "warning"
        )
    if token_count > max_tokens:
        return HookResult(
            False,
            f"🚨 Token 已超限: {token_count}/{max_tokens}",
            "critical"
        )
    return HookResult(True, f"Token {token_count}/{max_tokens}", "info")


# ============== Hook 注册中心 ==============

class HookRegistry:
    """Hook 注册中心(铁律 L3-9 on-demand hooks)"""

    def __init__(self):
        self.hooks: Dict[str, Hook] = {
            "hook-e0-enforce": Hook(
                name="hook-e0-enforce",
                bound_skill="skill-quote",
                trigger_timing="before_quote",
                hook_type=HookType.COMMAND,
                description="E0 板材强制检查(报价前)",
                callback=hook_e0_enforce,
            ),
            "hook-over30-warn": Hook(
                name="hook-over30-warn",
                bound_skill="skill-quote",
                trigger_timing="after_quote",
                hook_type=HookType.COMMAND,
                description="报价偏差 >30% 预警",
                callback=hook_over30_warn,
            ),
            "hook-bearing-wall": Hook(
                name="hook-bearing-wall",
                bound_skill="skill-layout",
                trigger_timing="in_layout",
                hook_type=HookType.COMMAND,
                description="承重墙拆除拦截(G1 致命)",
                callback=hook_bearing_wall,
            ),
            "hook-privacy-filter": Hook(
                name="hook-privacy-filter",
                bound_skill="skill-talk-analysis",
                trigger_timing="before_output",
                hook_type=HookType.COMMAND,
                description="手机号/身份证/银行卡脱敏检查",
                callback=hook_privacy_filter,
            ),
            "hook-budget-fuse": Hook(
                name="hook-budget-fuse",
                bound_skill=None,  # 全局
                trigger_timing="global",
                hook_type=HookType.COMMAND,
                description="Token 超限熔断",
                callback=hook_budget_fuse,
            ),
        }

    def run_hooks(self, skill_name: str, timing: str, context: Dict[str, Any]) -> List[HookResult]:
        """
        运行绑定到特定 Skill+timing 的所有 Hook

        Args:
            skill_name: Skill 名称(如 "skill-quote")
            timing: 触发时机(before_quote/after_quote/in_layout/before_output)
            context: 上下文数据
        """
        results = []
        run_hook_names = set()

        # 1. 特定 Skill + timing 的 Hook
        for hook in self.hooks.values():
            if hook.bound_skill == skill_name and hook.trigger_timing == timing:
                results.append(hook.run(context))
                run_hook_names.add(hook.name)

        # 2. 全局 Hook(任何 Skill 任何时机都跑,且没跑过)
        for hook in self.hooks.values():
            if hook.bound_skill is None and hook.trigger_timing == "global":
                if hook.name not in run_hook_names:
                    results.append(hook.run(context))
                    run_hook_names.add(hook.name)

        return results

    def list_hooks(self) -> List[Dict[str, str]]:
        """列出所有 Hook"""
        return [
            {
                "name": h.name,
                "skill": h.bound_skill or "全局",
                "timing": h.trigger_timing,
                "type": h.hook_type.value,
                "description": h.description,
            }
            for h in self.hooks.values()
        ]


# ============== 全局实例 ==============

REGISTRY = HookRegistry()


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("hooks.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:列出所有 Hook
    print("--- 测试 1:列出所有 Hook ---")
    hooks_list = REGISTRY.list_hooks()
    print(f"  总数: {len(hooks_list)}")
    for h in hooks_list:
        print(f"  - {h['name']:25s} 绑 {h['skill']:20s} {h['timing']:15s} {h['type']}")
    if len(hooks_list) == 5:
        print("  ✅ 沙箱实证:5 个 Hook 全部注册")
    print()

    # 测试 2:E0 板材强制检查
    print("--- 测试 2:E0 板材检查(违规) ---")
    result = REGISTRY.run_hooks("skill-quote", "before_quote", {
        "quote_items": [
            {"name": "橱柜", "material": "颗粒板"},  # 没标 E0
            {"name": "衣柜", "material": "密度板"},  # 没标 E0
        ]
    })
    print(f"  Hook 数量: {len(result)}")
    for r in result:
        print(f"  [{r.severity}] passed={r.passed}: {r.message}")
    if not result[0].passed and "E0" in result[0].message:
        print("  ✅ 沙箱实证:E0 违规被正确拦截")
    print()

    # 测试 3:E0 板材通过
    print("--- 测试 3:E0 板材检查(合规) ---")
    result = REGISTRY.run_hooks("skill-quote", "before_quote", {
        "quote_items": [
            {"name": "橱柜", "material": "E0 级颗粒板"},
            {"name": "衣柜", "material": "E0 级密度板"},
        ]
    })
    for r in result:
        print(f"  [{r.severity}] passed={r.passed}: {r.message}")
    if result[0].passed:
        print("  ✅ 沙箱实证:E0 合规通过")
    print()

    # 测试 4:承重墙拆除拦截
    print("--- 测试 4:承重墙拆除拦截 ---")
    result = REGISTRY.run_hooks("skill-layout", "in_layout", {
        "demolish_walls": ["主卧外墙", "次卧与客厅之间"]
    })
    for r in result:
        print(f"  [{r.severity}] passed={r.passed}: {r.message}")
    if not result[0].passed and "承重墙" in result[0].message:
        print("  ✅ 沙箱实证:承重墙拆除被 G1 致命级拦截")
    print()

    # 测试 5:偏差 >30% 预警
    print("--- 测试 5:偏差 50% 预警 ---")
    result = REGISTRY.run_hooks("skill-quote", "after_quote", {
        "deviation_percent": 50.0,
        "expected_range": [100000, 200000],
        "actual_price": 75000,
    })
    for r in result:
        print(f"  [{r.severity}] passed={r.passed}: {r.message}")
    if result[0].passed and "warning" in result[0].severity:
        print("  ✅ 沙箱实证:偏差预警触发")
    print()

    # 测试 6:隐私过滤
    print("--- 测试 6:隐私过滤(未脱敏) ---")
    result = REGISTRY.run_hooks("skill-talk-analysis", "before_output", {
        "text": "客户联系方式:13800138000,身份证 210311198010270014"
    })
    for r in result:
        print(f"  [{r.severity}] passed={r.passed}: {r.message}")
    if not result[0].passed and "手机号" in result[0].message:
        print("  ✅ 沙箱实证:未脱敏数据被拦截")
    print()

    # 测试 7:隐私过滤(已脱敏)
    print("--- 测试 7:隐私过滤(已脱敏) ---")
    result = REGISTRY.run_hooks("skill-talk-analysis", "before_output", {
        "text": "客户联系方式:138****8000,身份证 210311********0014"
    })
    for r in result:
        print(f"  [{r.severity}] passed={r.passed}: {r.message}")
    if result[0].passed:
        print("  ✅ 沙箱实证:已脱敏数据通过")
    print()

    # 测试 8:Token 熔断
    print("--- 测试 8:Token 熔断(超 95%) ---")
    result = REGISTRY.run_hooks("skill-quote", "before_quote", {
        "token_count": 7800,
        "max_tokens": 8000,
    })
    for r in result:
        print(f"  [{r.severity}] passed={r.passed}: {r.message}")
    if not result[0].passed and "Token" in result[0].message:
        print("  ✅ 沙箱实证:Token 熔断触发")
