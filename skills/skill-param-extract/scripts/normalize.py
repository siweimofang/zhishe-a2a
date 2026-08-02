#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
normalize.py · 参数标准化脚本
铁律 L3-8:确定性操作封装为脚本

Author: Mavis
Date: 2026-06-26
"""

import json
from typing import Dict, Any, List, Tuple


# 默认值
DEFAULT_HEIGHT = 2.8
DEFAULT_DOORS = 1
DEFAULT_WINDOWS = 1
DEFAULT_FLOOR_TYPE = "木地板"
DEFAULT_WALL_TYPE = "乳胶漆"


def normalize_params(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    标准化参数 + 返回缺失项警告

    Returns:
        (标准化后参数, 警告列表)
    """
    warnings = []
    result = {}

    # 1. 必填项
    for field in ["city", "district", "total_area", "package_type", "tier"]:
        if field not in raw or not raw[field]:
            warnings.append(f"缺失必填项: {field}")
            return {}, warnings
        result[field] = raw[field]

    # 2. 数字字段
    try:
        result["total_area"] = float(raw["total_area"])
        if result["total_area"] <= 0 or result["total_area"] > 1000:
            warnings.append(f"总面积 {result['total_area']} 异常(应在 1-1000 平米)")
    except (ValueError, TypeError):
        warnings.append(f"总面积格式错误: {raw['total_area']}")
        return {}, warnings

    # 3. 房间数
    result["room_count"] = int(raw.get("room_count", 0))
    if result["room_count"] <= 0:
        warnings.append("房间数缺失或 <= 0")
        return {}, warnings

    # 4. 房间列表(可选,没有就用默认 1 个)
    rooms = raw.get("rooms", [])
    if not rooms:
        warnings.append("无房间详情,使用默认(1 个 5x4 平米客厅)")
        rooms = [{"name": "客厅", "length": 5.0, "width": 4.0}]

    normalized_rooms = []
    for r in rooms:
        nr = {
            "name": r.get("name", "未命名"),
            "length": float(r.get("length", 4.0)),
            "width": float(r.get("width", 3.0)),
            "height": float(r.get("height", DEFAULT_HEIGHT)),
            "doors": int(r.get("doors", DEFAULT_DOORS)),
            "windows": int(r.get("windows", DEFAULT_WINDOWS)),
            "floor_type": r.get("floor_type", DEFAULT_FLOOR_TYPE),
            "wall_type": r.get("wall_type", DEFAULT_WALL_TYPE),
        }
        normalized_rooms.append(nr)
    result["rooms"] = normalized_rooms

    # 5. 可选项
    result["orientation"] = raw.get("orientation", "南")
    result["floor_number"] = int(raw.get("floor_number", 1))
    result["decoration_age"] = raw.get("decoration_age", "新房")
    result["has_elevator"] = bool(raw.get("has_elevator", True))
    result["is_corner"] = bool(raw.get("is_corner", False))

    return result, warnings


def validate_city_district(city: str, district: str, config: Dict[str, Any]) -> bool:
    """检查城市/区是否在基准价库"""
    cities = config.get("cities", {})
    if city not in cities:
        return False
    districts = cities[city].get("districts", {})
    return district in districts


# ============== 沙箱自测 ==============
if __name__ == "__main__":
    print("=" * 60)
    print("normalize.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:完整参数
    print("--- 测试 1:完整参数 ---")
    raw1 = {
        "city": "沈阳", "district": "浑南", "total_area": 89,
        "room_count": 8, "package_type": "半包", "tier": "中档",
        "rooms": [
            {"name": "客厅", "length": 4.5, "width": 4.0},
            {"name": "主卧", "length": 4.2, "width": 3.6},
        ],
        "orientation": "南", "floor_number": 5, "has_elevator": True,
    }
    result, warnings = normalize_params(raw1)
    print(f"  标准化结果: city={result.get('city')}, area={result.get('total_area')}, rooms={len(result.get('rooms', []))}")
    print(f"  警告: {warnings}")
    if not warnings:
        print("  ✅ 沙箱实证:完整参数标准化成功")
    print()

    # 测试 2:缺失必填项
    print("--- 测试 2:缺失 city ---")
    raw2 = {"district": "浑南", "total_area": 89, "package_type": "半包", "tier": "中档"}
    result, warnings = normalize_params(raw2)
    print(f"  警告: {warnings}")
    if "缺失必填项" in warnings[0]:
        print("  ✅ 沙箱实证:缺失项正确报错")
    print()

    # 测试 3:无效面积
    print("--- 测试 3:无效面积 1500 平米 ---")
    raw3 = {"city": "沈阳", "district": "浑南", "total_area": 1500, "package_type": "半包", "tier": "中档", "room_count": 5}
    result, warnings = normalize_params(raw3)
    print(f"  警告: {warnings}")
    if warnings and "异常" in warnings[0]:
        print("  ✅ 沙箱实证:异常面积正确报错")
    print()

    # 测试 4:无房间详情
    print("--- 测试 4:无房间详情 ---")
    raw4 = {"city": "沈阳", "district": "浑南", "total_area": 89, "package_type": "半包", "tier": "中档", "room_count": 3}
    result, warnings = normalize_params(raw4)
    print(f"  默认房间数: {len(result.get('rooms', []))}")
    print(f"  警告: {warnings}")
    if len(result.get('rooms', [])) == 1:
        print("  ✅ 沙箱实证:无房间详情自动补充默认")
    print()

    # 测试 5:城市校验
    print("--- 测试 5:城市校验 ---")
    import os
    from pathlib import Path
    cfg_path = Path(__file__).parent.parent.parent.parent / "data" / "city_pricing.json"
    config = json.load(open(cfg_path, encoding="utf-8"))
    if validate_city_district("沈阳", "浑南", config):
        print("  ✅ 沙箱实证:沈阳浑南存在")
    if not validate_city_district("伦敦", "中心", config):
        print("  ✅ 沙箱实证:伦敦不存在,正确拒绝")
