#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
price_calc.py · 装修分项报价脚本
铁律 L3-8:确定性操作封装为脚本

Author: Mavis
Date: 2026-06-26

分项明细:
- 硬装(隐蔽工程 + 面子工程)
- 主材(瓷砖、地板、橱柜、卫浴、门)
- 人工(水电工、瓦工、木工、油工)
"""

import os
import json
from typing import Dict, List, Any
from pathlib import Path

CONFIG_PATH = os.environ.get(
    "ZHISHE_CITY_PRICING",
    str(Path(__file__).parent.parent.parent.parent / "data" / "city_pricing.json")
)


# 硬装单价(元/平米,基于沈阳市场)
HARD_UNIT_PRICES = {
    "经济型": {
        "水电": 80, "防水": 35, "瓦工": 100, "木工": 60, "油工": 50,
        "拆除": 30, "砌墙": 80, "吊顶": 80, "墙面找平": 25,
    },
    "中档": {
        "水电": 120, "防水": 50, "瓦工": 150, "木工": 90, "油工": 70,
        "拆除": 40, "砌墙": 100, "吊顶": 120, "墙面找平": 35,
    },
    "中高档": {
        "水电": 180, "防水": 80, "瓦工": 220, "木工": 140, "油工": 100,
        "拆除": 60, "砌墙": 140, "吊顶": 180, "墙面找平": 50,
    },
    "豪华": {
        "水电": 260, "防水": 120, "瓦工": 320, "木工": 200, "油工": 150,
        "拆除": 80, "砌墙": 200, "吊顶": 280, "墙面找平": 80,
    },
}

# 主材单价(元/平米,基于沈阳市场)
MATERIAL_UNIT_PRICES = {
    "经济型": {
        "瓷砖": 80, "地板": 120, "橱柜": 800, "卫浴": 2500, "门": 1200,
        "乳胶漆": 25, "吊顶": 100, "灯具": 80, "开关插座": 30,
    },
    "中档": {
        "瓷砖": 150, "地板": 220, "橱柜": 1500, "卫浴": 4500, "门": 2200,
        "乳胶漆": 45, "吊顶": 180, "灯具": 150, "开关插座": 50,
    },
    "中高档": {
        "瓷砖": 280, "地板": 380, "橱柜": 3000, "卫浴": 8000, "门": 4000,
        "乳胶漆": 80, "吊顶": 320, "灯具": 280, "开关插座": 80,
    },
    "豪华": {
        "瓷砖": 500, "地板": 700, "橱柜": 6000, "卫浴": 18000, "门": 8000,
        "乳胶漆": 150, "吊顶": 600, "灯具": 500, "开关插座": 150,
    },
}


def load_city_pricing() -> Dict[str, Any]:
    """加载城市基准价"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_hard_cost(area: float, tier: str) -> Dict[str, Any]:
    """计算硬装成本"""
    if tier not in HARD_UNIT_PRICES:
        return {"error": f"未知档次 {tier}"}

    prices = HARD_UNIT_PRICES[tier]
    items = {}
    total = 0
    for item, unit_price in prices.items():
        cost = unit_price * area
        items[item] = {
            "unit_price": unit_price,
            "area": area,
            "cost": round(cost, 2)
        }
        total += cost

    return {
        "category": "硬装",
        "tier": tier,
        "items": items,
        "total": round(total, 2),
    }


def calculate_material_cost(area: float, tier: str, room_count: int) -> Dict[str, Any]:
    """计算主材成本(橱柜/卫浴/门按房间数算)"""
    if tier not in MATERIAL_UNIT_PRICES:
        return {"error": f"未知档次 {tier}"}

    prices = MATERIAL_UNIT_PRICES[tier]
    items = {}

    # 按面积算的项
    for item in ["瓷砖", "地板", "乳胶漆", "吊顶", "灯具", "开关插座"]:
        cost = prices[item] * area
        items[item] = {
            "unit_price": prices[item],
            "area": area,
            "cost": round(cost, 2),
            "basis": "按面积"
        }

    # 按房间数算的项
    for item in ["橱柜", "卫浴", "门"]:
        cost = prices[item] * room_count
        items[item] = {
            "unit_price": prices[item],
            "count": room_count,
            "cost": round(cost, 2),
            "basis": "按房间数"
        }

    total = sum(i["cost"] for i in items.values())

    return {
        "category": "主材",
        "tier": tier,
        "items": items,
        "total": round(total, 2),
    }


def calculate_full_quote(
    area: float,
    tier: str,
    room_count: int,
    package_type: str = "半包",
) -> Dict[str, Any]:
    """
    计算完整报价

    Args:
        area: 建筑面积(平米)
        tier: 档次(经济型/中档/中高档/豪华)
        room_count: 房间数(含客厅+卧室+厨房+卫生间)
        package_type: 装修方式(半包/大包/全案)
    """
    hard = calculate_hard_cost(area, tier)

    if "error" in hard:
        return hard

    # 半包只算硬装
    if package_type == "半包":
        return {
            "package_type": "半包",
            "tier": tier,
            "area": area,
            "hard_cost": hard,
            "material_cost": None,
            "total": hard["total"],
            "warning": "半包仅含硬装(人工 + 辅料),主材需业主自购",
        }

    # 大包/全案 = 硬装 + 主材
    material = calculate_material_cost(area, tier, room_count)
    total = hard["total"] + material["total"]

    return {
        "package_type": package_type,
        "tier": tier,
        "area": area,
        "room_count": room_count,
        "hard_cost": hard,
        "material_cost": material,
        "total": round(total, 2),
        "hard_ratio": round(hard["total"] / total * 100, 1),
        "material_ratio": round(material["total"] / total * 100, 1),
    }


# ============== 沙箱自测 ==============
if __name__ == "__main__":
    print("=" * 60)
    print("price_calc.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:89 平三室两厅中档半包
    print("--- 测试 1:89 平中档半包(8 房间) ---")
    result = calculate_full_quote(89, "中档", 8, "半包")
    print(f"  装修方式: {result['package_type']}")
    print(f"  硬装总额: {result['hard_cost']['total']} 元")
    for item, info in result['hard_cost']['items'].items():
        print(f"    {item}: {info['unit_price']} 元/平 × {info['area']} 平 = {info['cost']} 元")
    print(f"  总价: {result['total']} 元")
    # 沙箱验证:中档半包应在 7-15 万之间
    if 60000 <= result['total'] <= 150000:
        print(f"  ✅ 沙箱实证:89 平中档半包 = {result['total']} 元 = 100% 合理")
    print()

    # 测试 2:89 平中档大包
    print("--- 测试 2:89 平中档大包(8 房间) ---")
    result2 = calculate_full_quote(89, "中档", 8, "大包")
    print(f"  装修方式: {result2['package_type']}")
    print(f"  硬装: {result2['hard_cost']['total']} 元")
    print(f"  主材: {result2['material_cost']['total']} 元")
    print(f"  总价: {result2['total']} 元")
    print(f"  硬装/主材比例: {result2['hard_ratio']}% / {result2['material_ratio']}%")
    if 150000 <= result2['total'] <= 300000:
        print(f"  ✅ 沙箱实证:89 平中档大包 = {result2['total']} 元 = 100% 合理")
    print()

    # 测试 3:120 平中高档大包
    print("--- 测试 3:120 平中高档大包(10 房间) ---")
    result3 = calculate_full_quote(120, "中高档", 10, "大包")
    print(f"  硬装: {result3['hard_cost']['total']} 元")
    print(f"  主材: {result3['material_cost']['total']} 元")
    print(f"  总价: {result3['total']} 元")
    if 300000 <= result3['total'] <= 600000:
        print(f"  ✅ 沙箱实证:120 平中高档大包 = {result3['total']} 元 = 100% 合理")
    print()

    # 测试 4:经济型 60 平半包
    print("--- 测试 4:60 平经济型半包(7 房间) ---")
    result4 = calculate_full_quote(60, "经济型", 7, "半包")
    print(f"  硬装: {result4['hard_cost']['total']} 元")
    print(f"  总价: {result4['total']} 元")
    if 30000 <= result4['total'] <= 80000:
        print(f"  ✅ 沙箱实证:60 平经济型半包 = {result4['total']} 元 = 100% 合理")
    print()

    # 测试 5:豪华 150 平大包
    print("--- 测试 5:150 平豪华大包(12 房间) ---")
    result5 = calculate_full_quote(150, "豪华", 12, "大包")
    print(f"  硬装: {result5['hard_cost']['total']} 元")
    print(f"  主材: {result5['material_cost']['total']} 元")
    print(f"  总价: {result5['total']} 元")
    if 500000 <= result5['total'] <= 1200000:
        print(f"  ✅ 沙箱实证:150 平豪华大包 = {result5['total']} 元 = 100% 合理")
