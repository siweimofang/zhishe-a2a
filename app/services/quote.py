"""
报价引擎 V1.0 (2026-06-13) + V6.0 (2026-06-26 Anthropic Skills 升级)

业务铁律(用户 domain expert 教):
- 装修不是房地产
- 装修报价 = 施工工艺标准 × 工程量,但前期接触业主时用"面积 × 单价"估算
- 半包/大包/全案 严格区分
- 报价前必问"哪种方式 + 哪个档次"

V1.0 实现: 纯函数查表,数据从 data/quote_baseline.json 读
V2.0+: 加分项工程量计算、加系数(户型/风格/面积分段)、加 RAG
V6.0: 集成 Anthropic Skills 架构(L3 原则 3-8)
  - 调用 skills/skill-quote/scripts/price_check.py(偏差 >30% 预警)
  - 调用 skills/skill-quote/scripts/price_calc.py(分项报价)
  - 调用 skills/skill-quote/scripts/area_calc.py(面积计算)
  - 调用 data/city_pricing.json(13 城 52 区基准价)
  - 调用 skills/skill-layout/scripts/constraint_check.py(布局约束)
  - 调用 skills/skill-param-extract/scripts/normalize.py(参数标准化)
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("quote")

DATA_FILE = Path(__file__).parent.parent.parent / "data" / "quote_baseline.json"


def _load_baseline() -> dict:
    """读报价基线数据(每次调用重读,允许运行时改文件热加载)"""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def estimate(
    package: str,
    tier: str,
    area: float,
    *,
    house_type: Optional[str] = None,
    style: Optional[str] = None,
) -> Optional[dict]:
    """
    前期估算(场景 A): 用"面积 × 单价"快速给业主参考范围

    Args:
        package: 半包 / 大包 / 全案设计
        tier: 经济 / 中端 / 高端 / 豪华
        area: 建筑面积(平方米)
        house_type: 户型(V2.0 加系数, V1.0 留口子)
        style: 风格(V2.0 加系数, V1.0 留口子)

    Returns:
        {
            "package": "半包",
            "tier": "中端",
            "area": 90,
            "unit_min": 450,
            "unit_max": 600,
            "unit_median": 525,
            "total_min": 40500,
            "total_max": 54000,
            "total_median": 47250,
            "承接单位主体": "装修公司",
            "description": "包人工+辅材...",
            "note": "估算,不是合同价"
        }
        或 None(全案设计无标准区间)
    """
    baseline = _load_baseline()
    pkg_data = baseline["baseline"].get(package)
    if not pkg_data:
        return None

    # 全案设计:返回 None,让 LLM 走"一房一价"路径
    if package == "全案设计":
        return {
            "package": "全案设计",
            "tier": tier,
            "area": area,
            "unit_min": None,
            "unit_max": None,
            "unit_median": None,
            "total_min": None,
            "total_max": None,
            "total_median": None,
            "承接单位主体": pkg_data.get("承接单位主体", "设计工作室 / 设计公司"),
            "description": pkg_data.get("description", ""),
            "note": "全案设计无标准区间,需单独报价(一房一价)",
        }

    tier_data = pkg_data.get(tier)
    if not tier_data:
        return None

    return {
        "package": package,
        "tier": tier,
        "area": area,
        "house_type": house_type,
        "style": style,
        "unit_min": tier_data["min"],
        "unit_max": tier_data["max"],
        "unit_median": tier_data["median"],
        "total_min": round(area * tier_data["min"], 2),
        "total_max": round(area * tier_data["max"], 2),
        "total_median": round(area * tier_data["median"], 2),
        "承接单位主体": pkg_data.get("承接单位主体", "装修公司"),
        "description": pkg_data.get("description", ""),
        "note": "估算,不是合同价(签约前必须让装修公司上门量房出分项报价)",
    }


def breakdown_estimate(package: str, tier: str, total_median: float) -> dict:
    """
    分项拆解(场景 B): 按百分比把总价拆成 人工/材料/管理/设计 等分项
    用于"用户问具体怎么算"时给真实报价分项

    Returns:
        {
            "人工费": {"pct": 0.55, "amount": 26400},
            "辅材费": {"pct": 0.35, "amount": 16800},
            "管理费": {"pct": 0.10, "amount": 4800}
        }
    """
    baseline = _load_baseline()
    pct_data = baseline["breakdown_pct"].get(package, {})
    result = {}
    for item, pct in pct_data.items():
        result[item] = {
            "pct": pct,
            "amount": round(total_median * pct, 2),
        }
    return result


# ============================================================
# 用户输入解析(用正则粗提取,LLM 兜底)
# ============================================================

PACKAGE_KEYWORDS = {
    "半包": ["半包"],
    "大包": ["大包", "全包"],
    "全案设计": ["全案", "全案设计", "私人定制", "整装"],
}

TIER_KEYWORDS = {
    "经济": ["经济", "低端", "简装", "便宜"],
    "中端": ["中端", "中档", "中等", "普通"],
    "高端": ["高端", "高档", "高"],
    "豪华": ["豪华", "顶配", "奢侈"],
}


def parse_user_intent(text: str) -> dict:
    """
    从用户文本里粗提取 (package, tier, area)
    LLM 会基于这个做最终决策
    """
    result = {"package": None, "tier": None, "area": None}

    # package
    for pkg, kws in PACKAGE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            result["package"] = pkg
            break

    # tier
    for tier, kws in TIER_KEYWORDS.items():
        if any(kw in text for kw in kws):
            result["tier"] = tier
            break

    # area: 找数字 + 平/平米/平方米/㎡
    area_patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:平|平米|平方米|㎡|m[²2])",
        r"(\d+(?:\.\d+)?)\s*平方",
        r"面积\s*(\d+(?:\.\d+)?)",
    ]
    for pat in area_patterns:
        m = re.search(pat, text)
        if m:
            try:
                result["area"] = float(m.group(1))
                break
            except (ValueError, IndexError):
                pass

    return result


def format_estimate_for_llm(est: dict) -> str:
    """
    把 estimate() 结果格式化成可注入 LLM prompt 的文本
    LLM 看到这段话就不会瞎编价格
    """
    if est["unit_min"] is None:
        return f"""[精确数据 - quote_baseline.json 查表结果]
用户问:{est['package']} / {est['tier']} / {est['area']}平
结论:全案设计无标准区间,一房一价。
承接单位:{est['承接单位主体']}
说明:{est['description']}"""

    return f"""[精确数据 - quote_baseline.json 查表结果]
用户问:{est['package']} / {est['tier']} / {est['area']}平
单价区间:{est['unit_min']}-{est['unit_max']} 元/平 (中位数 {est['unit_median']})
总价区间:{est['total_min']:.0f}-{est['total_max']:.0f} 元 (中位数 {est['total_median']:.0f} 元)
承接单位:{est['承接单位主体']}
说明:{est['description']}
    重要:这是估算范围,不是合同价。签约前必须让装修公司上门量房出分项报价。"""


# ============================================================
# V6.0 Anthropic Skills 集成(L3 原则 3-8)
# ============================================================
import sys
import importlib.util
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


# Tier 标准化映射(V1.0 baseline 用 经济/中端/高端/豪华,V6.0 Skills 用 经济型/中档/中高档/豪华)
TIER_MAPPING = {
    "经济": "经济型", "经济型": "经济型",
    "中端": "中档", "中档": "中档", "中等": "中档",
    "中高档": "中高档",
    "高端": "豪华", "豪华": "豪华",
}


def normalize_tier(tier: str) -> str:
    """标准化 tier 名称(V1.0 → V6.0)"""
    return TIER_MAPPING.get(tier, tier)


def _load_skill_script(skill_name: str, script_name: str):
    """动态加载 skills/{skill_name}/scripts/{script_name}.py"""
    script_path = SKILLS_DIR / skill_name / "scripts" / f"{script_name}.py"
    if not script_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{script_name}", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def full_quote_v6(
    city: str,
    district: str,
    area: float,
    tier: str,
    package_type: str,
    room_count: int = 6,
    client_price: float = None,
) -> dict:
    """
    V6.0 完整报价(Skills 架构)

    Args:
        city: 城市
        district: 区
        area: 建筑面积
        tier: 经济型/中档/中高档/豪华
        package_type: 半包/大包/全案
        room_count: 房间数
        client_price: 客户报价(用于偏差校验,可选)

    Returns:
        {
            "phase_1_baseline": estimate(),
            "phase_2_skill_calc": price_calc.calculate_full_quote(),
            "phase_3_price_check": price_check.validate_quote(),
            "warning": ...
        }
    """
    # Phase 1: 原有 baseline 估算(V1.0 tier = 经济/中端/高端/豪华)
    phase_1 = estimate(package_type, tier, area)
    if phase_1 is None:
        return {"error": "estimate() 返回 None", "phase_1": None}

    # 标准化 tier 给 V6.0 Skills 用(经济/中端/高端/豪华 → 经济型/中档/中高档/豪华)
    tier_v6 = normalize_tier(tier)

    # Phase 2: Skill-quote 计算(L3 原则 8 确定性脚本)
    price_calc_mod = _load_skill_script("skill-quote", "price_calc")
    phase_2 = price_calc_mod.calculate_full_quote(area, tier_v6, room_count, package_type)

    # Phase 3: 价格偏差校验(L3 原则 9 hook-over30-warn)
    if client_price is not None:
        price_check_mod = _load_skill_script("skill-quote", "price_check")
        phase_3 = price_check_mod.validate_quote(city, district, area, client_price, tier_v6, package_type)
    else:
        phase_3 = None

    # 整合
    result = {
        "city": city,
        "district": district,
        "area": area,
        "tier": tier,
        "package_type": package_type,
        "room_count": room_count,
        "phase_1_baseline": phase_1,
        "phase_2_skill_calc": phase_2,
        "phase_3_price_check": phase_3,
        "format_for_llm": format_estimate_for_llm(phase_1),
    }

    # 自动告警
    if phase_3 and phase_3.get("severe_deviation"):
        result["warning"] = f"⚠️ 价格偏差 {phase_3['deviation']}%,已超 30% 预警阈值: {phase_3.get('warning', '')}"

    return result


# ============================================================
# 单元测试入口
# ============================================================

if __name__ == "__main__":
    # 手动测试
    print("=== 测试 1: 半包中端 90 平 ===")
    est = estimate("半包", "中端", 90)
    print(json.dumps(est, ensure_ascii=False, indent=2))
    print()
    print(format_estimate_for_llm(est))
    print()

    print("=== 测试 2: 大包高端 130 平 ===")
    est = estimate("大包", "高端", 130)
    print(json.dumps(est, ensure_ascii=False, indent=2))
    print()

    print("=== 测试 3: 全案设计 200 平 ===")
    est = estimate("全案设计", "豪华", 200)
    print(format_estimate_for_llm(est))
    print()

    print("=== 测试 4: 分项拆解(半包中端 90 平,中位价 47250) ===")
    bd = breakdown_estimate("半包", "中端", 47250)
    print(json.dumps(bd, ensure_ascii=False, indent=2))
    print()

    print("=== 测试 5: 解析用户输入 ===")
    tests = [
        "我家 90 平,想半包,大概多少钱?",
        "100 平全包,中档,沈阳大概多少?",
        "130 平米大包豪华档,需要多少预算?",
        "我家 200 平想做全案设计",
    ]
    for t in tests:
        print(f"  '{t}' -> {parse_user_intent(t)}")
