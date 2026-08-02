"""
Wait! 自纠错模块(Phase 1 · 2026-06-25)
参考 L3_GDPevo + L3_Qwen-AgentWorld
沙箱实证:L3 中"Wait!"触发自我修正机制,在 129 轮中 1347 次,平均每轮 10.4 次。

3 道自纠错防线(基于 L3 实战经验):
1. 价格自纠错 - 报价 vs 市场基准偏离 >30% → 标记 + 警告
2. 逻辑自纠错 - 预算 + 装修方式 + 档次 三者矛盾 → 标记
3. 区域自纠错 - 当前只支持沈阳(quote_baseline.json city=沈阳),非沈阳用户 → 警告 + 引导
"""
from typing import Optional
import logging
import json

from app.services.quote import estimate, _load_baseline

log = logging.getLogger("wait_self_check")


# ============================================================
# 偏离阈值配置(可调)
# ============================================================

PRICE_DEVIATION_THRESHOLD = 0.30  # 30% 偏离即标记(沙箱:实测沈阳区域基准)
LOGIC_CHECK_ENABLED = True
CITY_RESTRICTION_ENABLED = True


def wait_self_check(
    package: str,
    tier: str,
    area: float,
    *,
    user_text: Optional[str] = None,
    estimated_total: Optional[float] = None,
    city: Optional[str] = None,
) -> dict:
    """
    Phase 1 自纠错入口

    Returns:
        {
            "has_warning": bool,
            "warnings": [str],
            "confidence": "high" | "medium" | "low",
            "suggestion": str,
        }
    """
    warnings = []

    # === 检查 1:价格自纠错 ===
    if estimated_total is not None and area > 0:
        unit_price = estimated_total / area
        baseline = _load_baseline()

        # 找对应档位的基准单价
        pkg_data = baseline["baseline"].get(package, {})
        tier_data = pkg_data.get(tier, {})

        if tier_data and tier_data.get("min") is not None:
            base_min = tier_data["min"]
            base_max = tier_data["max"]
            base_median = tier_data["median"]

            # 计算偏离度
            deviation_low = (unit_price - base_min) / base_min if base_min > 0 else 0
            deviation_high = (unit_price - base_max) / base_max if base_max > 0 else 0

            if deviation_low < -PRICE_DEVIATION_THRESHOLD:
                warnings.append(
                    f"Wait! 单价 {unit_price:.0f} 元/平 低于市场基准最低 {base_min} 元/平 "
                    f"(低 {abs(deviation_low)*100:.0f}%),请检查是否漏报主材/辅材"
                )

            if deviation_high > PRICE_DEVIATION_THRESHOLD:
                warnings.append(
                    f"Wait! 单价 {unit_price:.0f} 元/平 高于市场基准最高 {base_max} 元/平 "
                    f"(高 {deviation_high*100:.0f}%),请检查档次匹配或区域差异"
                )

    # === 检查 2:逻辑自纠错 ===
    if LOGIC_CHECK_ENABLED:
        # 规则 A:预算 + 装修方式 + 档次 矛盾检测
        if user_text:
            logic_warnings = _check_user_logic(user_text, package, tier, area)
            warnings.extend(logic_warnings)

        # 规则 B:面积 + 户型 矛盾(小户型做大包全进口材料 = 矛盾)
        if area < 50 and tier in ["高端", "豪华"]:
            warnings.append(
                f"Wait! {area} 平做{tier}档 = 户型小但档次高,需确认业主实际需求"
            )

        # 规则 C:全案设计 + 经济/中端档 = 不匹配
        if package == "全案设计" and tier in ["经济", "中端"]:
            warnings.append(
                f"Wait! 全案设计是私人定制一房一价,与{tier}档标准化思维不匹配"
            )

    # === 检查 3:区域自纠错(诚实告知,不主动贴区域标签)===
    # 原则:不主动贴区域标签,但用户问到城市时诚实告知基线范围
    # 战略:"修内功不说,用户自然体会到"
    if CITY_RESTRICTION_ENABLED and city and city != "沈阳":
        baseline = _load_baseline()
        baseline_city = baseline.get("city", "沈阳")

        warnings.append(
            f"Wait! 当前价格基准参考{baseline_city}本地装修经验(行业内多年积累)。"
            f"{city}地区价格可能差异 ±20-30%(主材运费/人工成本/区域行情差异)。"
            f"建议:用这个参考范围作为心理价位,具体以{city}当地装修公司上门量房为准。"
            f"也可以切换到{baseline_city}本地装修顾问深入沟通。"
        )

    # === 置信度评估 ===
    if not warnings:
        confidence = "high"
        suggestion = "报价符合市场基准 + 逻辑一致 + 区域支持,可直接返回"
    elif len(warnings) == 1:
        confidence = "medium"
        suggestion = f"发现 1 个潜在问题:{warnings[0]}。建议在 LLM 回复前加备注。"
    else:
        confidence = "low"
        suggestion = f"发现 {len(warnings)} 个潜在问题,LLM 必须先解释再给报价。"

    return {
        "has_warning": len(warnings) > 0,
        "warnings": warnings,
        "confidence": confidence,
        "suggestion": suggestion,
    }


def _check_user_logic(user_text: str, package: str, tier: str, area: float) -> list:
    """检测用户输入的逻辑矛盾"""
    warnings = []

    text = user_text.lower()

    # 矛盾 1:预算低 + 高档材料
    if tier in ["高端", "豪华"] and any(kw in text for kw in ["预算", "钱", "花费", "便宜"]):
        if "预算" in text:
            warnings.append(
                f"Wait! 用户提到预算 + 选{tier}档,需确认预算范围是否覆盖{tier}档报价"
            )

    # 矛盾 2:小户型 + 多房间
    if area < 60 and any(kw in text for kw in ["三室", "四室", "5 室", "5室"]):
        warnings.append(
            f"Wait! {area} 平做多房间 = 房间紧凑,业主预期可能与实际不符"
        )

    # 矛盾 3:大包 + 主材用户买(语义冲突)
    if package == "大包" and any(kw in text for kw in ["自己买主材", "自购主材", "主材自己"]):
        warnings.append(
            f"Wait! 大包是'主材+辅材+人工全包',与用户'自己买主材'矛盾 → 应选半包"
        )

    # 矛盾 4:半包 + 不要辅材
    if package == "半包" and any(kw in text for kw in ["不要辅材", "不买辅材", "辅材自己"]):
        warnings.append(
            f"Wait! 半包包含辅材,与用户'不要辅材'矛盾 → 应选清包(但当前系统不支持)"
        )

    # 矛盾 5:全案设计 + 标准化套餐期望
    if package == "全案设计" and any(kw in text for kw in ["套餐", "标准", "普通", "经济"]):
        warnings.append(
            f"Wait! 全案设计是私人定制,与用户期望'标准化套餐'矛盾"
        )

    return warnings


# ============================================================
# 集成入口(给 LLM 用)
# ============================================================

def wait_self_check_before_llm(
    package: str,
    tier: str,
    area: float,
    user_text: Optional[str] = None,
    city: Optional[str] = None,
) -> str:
    """
    给 LLM 用的自纠错文本(直接注入 prompt)

    Returns:
        警告文本(空字符串 = 无警告)
    """
    # 先用 quote engine 算出基准价
    est = estimate(package, tier, area)
    if est and est.get("total_median"):
        est_total = est["total_median"]
    else:
        est_total = None

    result = wait_self_check(
        package=package,
        tier=tier,
        area=area,
        user_text=user_text,
        estimated_total=est_total,
        city=city,
    )

    if not result["has_warning"]:
        return ""

    lines = ["\n[Wait! 自纠错检查结果]"]
    for w in result["warnings"]:
        lines.append(f"- {w}")
    lines.append(f"\n置信度:{result['confidence']}")
    lines.append(f"建议:{result['suggestion']}")
    return "\n".join(lines)


# ============================================================
# 单元测试
# ============================================================

if __name__ == "__main__":
    print("=== Wait! 自纠错单元测试 ===\n")

    # 测试 1:正常情况
    print("--- 测试 1:90 平半包中端(正常) ---")
    r = wait_self_check("半包", "中端", 90, user_text="我家 90 平想做半包中端")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print()

    # 测试 2:逻辑矛盾
    print("--- 测试 2:60 平做豪华档(小户型高矛盾) ---")
    r = wait_self_check("豪华档", "豪华", 45, user_text="我家 45 平想做豪华装修")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print()

    # 测试 3:大包 + 自购主材矛盾
    print("--- 测试 3:大包 + 自己买主材(矛盾) ---")
    r = wait_self_check("大包", "中端", 100, user_text="大包中端 100 平,但主材自己买")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print()

    # 测试 4:非沈阳城市
    print("--- 测试 4:北京用户(区域不支持) ---")
    r = wait_self_check("半包", "中端", 90, city="北京")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print()

    # 测试 5:集成接口
    print("--- 测试 5:LLM 集成文本 ---")
    text = wait_self_check_before_llm("半包", "中端", 90, user_text="想半包中端 90 平")
    print(text)