#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
price_check.py · 报价结果校验脚本
铁律 L3-8:确定性操作封装为脚本,不靠模型生成

Author: Mavis
Date: 2026-06-26
"""

import json
import os
from typing import Dict, List, Tuple, Any
from pathlib import Path


# 配置文件路径(支持从环境变量覆盖)
CONFIG_PATH = os.environ.get(
    "ZHISHE_CITY_PRICING",
    str(Path(__file__).parent.parent.parent.parent / "data" / "city_pricing.json")
)


def load_city_pricing() -> Dict[str, Any]:
    """加载 13 城 52 区基准价配置"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_quote(
    city: str,
    district: str,
    area: float,
    total_price: float,
    tier: str,
    package_type: str = "半包"
) -> Dict[str, Any]:
    """
    校验报价合理性

    Args:
        city: 城市名(沈阳/北京/上海/广州/深圳/杭州/成都/南京/武汉/西安/大连/长春/哈尔滨)
        district: 区域名
        area: 面积(平米)
        total_price: 客户报价(元)
        tier: 档次(经济型/中档/中高档/豪华)
        package_type: 装修方式(半包/大包/全案)

    Returns:
        {
            "valid": bool,
            "expected_range": [low, high],
            "deviation": float,  # 偏差百分比
            "warning": str or None,
            "city_coefficient": float,
            "tier": str
        }
    """
    config = load_city_pricing()
    cities = config.get("cities", {})

    # 1. 检查城市是否存在
    if city not in cities:
        return {
            "valid": False,
            "error": f"城市 {city} 不在基准价库(已支持: {list(cities.keys())})",
            "expected_range": None,
            "deviation": None,
        }

    city_info = cities[city]
    coefficient = city_info.get("coefficient", 1.0)
    districts = city_info.get("districts", {})

    # 2. 检查区域是否存在
    if district not in districts:
        return {
            "valid": False,
            "error": f"{city} 区域 {district} 不在基准价库(已支持: {list(districts.keys())})",
            "expected_range": None,
            "deviation": None,
        }

    district_info = districts[district]
    if tier not in district_info:
        return {
            "valid": False,
            "error": f"{tier} 不在该城市档次中(可选: {list(district_info.keys())})",
            "expected_range": None,
            "deviation": None,
        }

    # 3. 计算基准价区间(乘以城市系数)
    raw_range = district_info[tier]
    expected_low = raw_range[0] * coefficient * area
    expected_high = raw_range[1] * coefficient * area

    # 4. 大包 / 全案加价系数
    if package_type == "大包":
        expected_low *= 2.0
        expected_high *= 3.5
    elif package_type == "全案":
        expected_low *= 3.5
        expected_high *= 7.0

    # 5. 计算偏差
    if total_price < expected_low:
        deviation = (expected_low - total_price) / expected_low * 100
        warning = f"报价低于基准价 {deviation:.1f}%,可能存在漏项/低开高走风险"
    elif total_price > expected_high:
        deviation = (total_price - expected_high) / expected_high * 100
        warning = f"报价高于基准价 {deviation:.1f}%,可能存在过度营销/包含项过多"
    else:
        deviation = 0
        warning = None

    # 6. 偏差 > 30% 强制预警(铁律 L3-9 hook-over30-warn)
    severe_deviation = abs(deviation) > 30

    return {
        "valid": True,
        "city": city,
        "district": district,
        "tier": tier,
        "package_type": package_type,
        "area": area,
        "city_coefficient": coefficient,
        "expected_range": [round(expected_low, 2), round(expected_high, 2)],
        "expected_unit": "元",
        "total_price": total_price,
        "deviation": round(deviation, 2),
        "warning": warning,
        "severe_deviation": severe_deviation,
    }


# ============== 沙箱自测(可直接 python price_check.py) ==============
if __name__ == "__main__":
    print("=" * 60)
    print("price_check.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:沈阳浑南 90 平中档半包,客户报价 4.5 万
    print("--- 测试 1:沈阳浑南 90 平中档半包,报价 4.5 万 ---")
    result = validate_quote("沈阳", "浑南", 90, 45000, "中档", "半包")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print()

    # 测试 2:北京朝阳 100 平中高档大包,报价 35 万(应该在范围内)
    print("--- 测试 2:北京朝阳 100 平中高档大包,报价 35 万 ---")
    result = validate_quote("北京", "朝阳", 100, 350000, "中高档", "大包")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print()

    # 测试 3:沈阳浑南 90 平中档半包,报价 2 万(严重偏低 预警)
    print("--- 测试 3:沈阳浑南 90 平中档半包,报价 2 万(严重偏低) ---")
    result = validate_quote("沈阳", "浑南", 90, 20000, "中档", "半包")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print()

    # 测试 4:不存在的城市
    print("--- 测试 4:不存在的城市 伦敦 ---")
    result = validate_quote("伦敦", "中心", 50, 100000, "中档")
    for k, v in result.items():
        print(f"  {k}: {v}")
