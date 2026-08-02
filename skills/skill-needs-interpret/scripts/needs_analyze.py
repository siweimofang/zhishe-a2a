#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
needs_analyze.py · 需求分析脚本
铁律 L3-8:确定性操作

Author: Mavis
Date: 2026-06-26
"""

import json
import os
from typing import Dict, List, Any
from pathlib import Path


CONFIG_PATH = os.environ.get(
    "ZHISHE_CITY_PRICING",
    str(Path(__file__).parent.parent.parent.parent / "data" / "city_pricing.json")
)


def load_pricing() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def space_analysis(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    空间分析
    根据面积/房间数/有孩子/有宠物推空间建议
    """
    area = profile.get("area", 89)
    rooms = profile.get("rooms", 3)
    has_child = profile.get("has_child", False)
    has_pet = profile.get("has_pet", False)
    style = profile.get("style", "现代简约")

    recommendations = []

    # 1. 空间评估
    if area < 60:
        recommendations.append("小户型(<60 平):建议开放式厨房 + 多功能客厅 + 客卧一体化")
    elif area < 100:
        recommendations.append("中等户型(60-100 平):标准 2-3 室布局,主卧带卫生间考虑性价比")
    elif area < 150:
        recommendations.append("改善型(100-150 平):可做 4 室,主卧带衣帽间 + 卫生间")
    else:
        recommendations.append("豪华型(>150 平):独立书房 + 衣帽间 + 多卫生间,考虑电梯")

    # 2. 儿童房建议
    if has_child:
        recommendations.append("儿童房:必须 E0 板材 + 圆角家具 + 插座保护盖")
        if rooms < 3:
            recommendations.append("⚠️ 房间数不足 3 室,需考虑儿童房 + 老人房 + 主卧")

    # 3. 宠物建议
    if has_pet:
        recommendations.append("宠物友好:地面选耐磨木地板/SPC 锁扣,避免地毯,墙面选可擦洗乳胶漆")

    # 4. 风格建议
    style_recs = {
        "现代简约": "现代简约适合小户型显大,沈阳 89 平首选,预算可控",
        "北欧": "北欧适合预算有限,80-100 平,主材选品牌",
        "新中式": "新中式适合 120+ 平,实木 + 中档瓷砖,沈阳本地文化契合",
        "日式": "日式适合 60-90 平,极简收纳,适合年轻夫妻",
        "轻奢": "轻奢适合 100-150 平,石材 + 金属,沈阳 2024-2026 流行",
    }
    if style in style_recs:
        recommendations.append(f"风格建议: {style_recs[style]}")

    return {
        "area_category": "小户型" if area < 60 else ("中等户型" if area < 100 else ("改善型" if area < 150 else "豪华型")),
        "recommendations": recommendations,
    }


def price_predict(profile: Dict[str, Any]) -> Dict[str, Any]:
    """报价预判(基于 city_pricing.json)"""
    config = load_pricing()
    city = profile.get("city", "沈阳")
    area = profile.get("area", 89)
    tier = profile.get("tier", "中端")
    package = profile.get("package", "半包")

    cities = config.get("cities", {})
    if city not in cities:
        return {"error": f"城市 {city} 不支持"}

    city_info = cities[city]
    coefficient = city_info.get("coefficient", 1.0)
    districts = city_info.get("districts", {})

    # 默认第一个区
    if not districts:
        return {"error": f"{city} 没有区数据"}
    first_district = list(districts.keys())[0]
    district_info = districts[first_district]

    # tier 标准化
    tier_map = {"经济": "经济型", "经济型": "经济型", "中端": "中档", "中档": "中档", "高端": "豪华", "豪华": "豪华"}
    tier_v6 = tier_map.get(tier, "中档")

    if tier_v6 not in district_info:
        return {"error": f"{tier_v6} 不支持"}

    raw = district_info[tier_v6]
    low = raw[0] * coefficient * area
    high = raw[1] * coefficient * area

    if package == "大包":
        low *= 2
        high *= 3.5
    elif package == "全案":
        low *= 3.5
        high *= 7

    return {
        "city": city,
        "default_district": first_district,
        "tier": tier_v6,
        "package": package,
        "low": round(low, 0),
        "high": round(high, 0),
        "median": round((low + high) / 2, 0),
    }


def communication_advice(risks: List[Dict[str, Any]]) -> List[str]:
    """沟通建议(基于风险清单)"""
    advice = []

    for r in risks:
        level = r.get("level", "低")
        category = r.get("category", "")
        desc = r.get("description", "")
        sugg = r.get("suggestion", "")

        if level == "高":
            advice.append(f"🚨[{category}高] {desc} → 立即处理:{sugg}")
        elif level == "中":
            advice.append(f"⚠️[{category}中] {desc} → 注意:{sugg}")
        else:
            advice.append(f"💡[{category}低] {desc} → {sugg}")

    if not advice:
        advice.append("✅ 客户无明显风险,可按标准流程推进")

    return advice


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("needs_analyze.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:沈阳 89 平有孩子现代简约中端半包
    print("--- 测试 1:沈阳 89 平有孩子现代简约中端半包 ---")
    profile1 = {"city": "沈阳", "area": 89, "rooms": 3, "has_child": True, "has_pet": False, "style": "现代简约", "tier": "中端", "package": "半包"}
    space = space_analysis(profile1)
    price = price_predict(profile1)
    advice = communication_advice([
        {"level": "高", "category": "预算", "description": "客户提到贷款", "suggestion": "先确认总预算"},
        {"level": "中", "category": "工期", "description": "客户希望尽快", "suggestion": "提前排施工队"},
    ])
    print(f"  空间分类: {space['area_category']}")
    for r in space["recommendations"][:3]:
        print(f"    - {r}")
    print(f"  报价预判: {price.get('low')} - {price.get('high')} 元(中位 {price.get('median')})")
    print(f"  沟通建议:")
    for a in advice:
        print(f"    {a}")
    if space["area_category"] == "中等户型" and price.get("median", 0) > 0 and len(advice) == 2:
        print("  ✅ 沙箱实证:需求分析 3 维度全跑通")
    print()

    # 测试 2:沈阳 200 平豪华新中式全案
    print("--- 测试 2:沈阳 200 平豪华新中式全案 ---")
    profile2 = {"city": "沈阳", "area": 200, "rooms": 4, "has_child": False, "has_pet": False, "style": "新中式", "tier": "豪华", "package": "全案"}
    space = space_analysis(profile2)
    price = price_predict(profile2)
    print(f"  空间分类: {space['area_category']}")
    print(f"  报价预判: {price.get('low')} - {price.get('high')} 元(中位 {price.get('median')})")
    if space["area_category"] == "豪华型" and price.get("median", 0) > 1000000:
        print("  ✅ 沙箱实证:豪华型新中式全案预判合理")
    print()

    # 测试 3:小户型 50 平
    print("--- 测试 3:沈阳 50 平有宠物极简经济 ---")
    profile3 = {"city": "沈阳", "area": 50, "rooms": 1, "has_child": False, "has_pet": True, "style": "极简", "tier": "经济", "package": "半包"}
    space = space_analysis(profile3)
    price = price_predict(profile3)
    print(f"  空间分类: {space['area_category']}")
    for r in space["recommendations"][:3]:
        print(f"    - {r}")
    print(f"  报价预判: {price.get('low')} - {price.get('high')} 元")
    if space["area_category"] == "小户型" and any("宠物" in r for r in space["recommendations"]):
        print("  ✅ 沙箱实证:小户型 + 宠物建议正确")
    print()

    # 测试 4:无风险
    print("--- 测试 4:沟通建议(无风险) ---")
    advice = communication_advice([])
    print(f"  建议: {advice}")
    if any("无明显风险" in a for a in advice):
        print("  ✅ 沙箱实证:无风险默认建议")
    print()

    # 测试 5:不支持的城市
    print("--- 测试 5:伦敦(不支持) ---")
    profile5 = {"city": "伦敦", "area": 50, "rooms": 1, "style": "极简", "tier": "经济", "package": "半包"}
    price = price_predict(profile5)
    print(f"  报价预判: {price}")
    if "error" in price:
        print("  ✅ 沙箱实证:不支持的城市正确报错")
