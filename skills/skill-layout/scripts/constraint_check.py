#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
constraint_check.py · 布局约束检查脚本
铁律 L3-8:确定性操作 + 铁律 L3-9 hook-bearing-wall

Author: Mavis
Date: 2026-06-26
"""

import json
from typing import Dict, List, Any, Tuple


# 承重墙标识(简化模型,实际需要结构图)
# 在生产环境应接入建筑结构图
DEFAULT_BEARING_WALLS = {
    "主卧外墙": True,
    "客厅外墙": True,
    "厨房外墙": True,
    "卫生间外墙": True,
    "阳台垛子": True,
    "客厅与电梯井之间": True,
}


def check_bearing_wall(wall_name: str) -> bool:
    """检查是否为承重墙"""
    return DEFAULT_BEARING_WALLS.get(wall_name, False)


def check_layout(layout: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    检查布局方案

    Returns:
        (是否通过, 错误列表)
    """
    errors = []

    # 1. 检查承重墙拆除(铁律 L3-9 G1 hook-bearing-wall)
    demolitions = layout.get("demolish_walls", [])
    for wall in demolitions:
        if check_bearing_wall(wall):
            errors.append(f"G1-致命: 承重墙 [{wall}] 不能拆除!")

    # 2. 检查卫生间门对卧室门
    bedroom_door = layout.get("bedroom_door_direction")
    bathroom_door = layout.get("bathroom_door_direction")
    if bedroom_door and bathroom_door and bedroom_door == bathroom_door:
        errors.append(f"G2-重要: 卧室门正对卫生间门(都是{bedroom_door}),建议做 L 型墙")

    # 3. 检查厨房燃气管
    kitchen_cabinet = layout.get("kitchen_cabinet", {})
    if kitchen_cabinet.get("encase_gas_pipe", False):
        errors.append("G2-重要: 厨房燃气管不能包死,橱柜必须预留检修口")

    # 4. 检查餐桌周围空间
    dining_table = layout.get("dining_table", {})
    if dining_table.get("clearance_cm", 90) < 90:
        errors.append(f"G3-经验: 餐桌周围至少留 90cm,当前 {dining_table.get('clearance_cm')}cm")

    # 5. 检查卫生间位置改动
    if layout.get("relocate_bathroom", False):
        errors.append("G2-重要: 卫生间沉箱不能改位置,只能在原位置调整")

    return len(errors) == 0, errors


# ============== 沙箱自测 ==============
if __name__ == "__main__":
    print("=" * 60)
    print("constraint_check.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:拆除承重墙(必须拒绝)
    print("--- 测试 1:拆除承重墙(主卧外墙) ---")
    layout1 = {"demolish_walls": ["主卧外墙"]}
    passed, errors = check_layout(layout1)
    print(f"  通过: {passed}")
    print(f"  错误: {errors}")
    if not passed and "承重墙" in errors[0]:
        print("  ✅ 沙箱实证:承重墙拆除被正确拒绝")
    print()

    # 测试 2:门对门
    print("--- 测试 2:卧室门正对卫生间门 ---")
    layout2 = {"bedroom_door_direction": "北", "bathroom_door_direction": "北"}
    passed, errors = check_layout(layout2)
    print(f"  错误: {errors}")
    if errors and "正对" in errors[0]:
        print("  ✅ 沙箱实证:门对门被正确警告")
    print()

    # 测试 3:燃气管包死
    print("--- 测试 3:厨房燃气管包死 ---")
    layout3 = {"kitchen_cabinet": {"encase_gas_pipe": True}}
    passed, errors = check_layout(layout3)
    print(f"  错误: {errors}")
    if errors and "燃气管" in errors[0]:
        print("  ✅ 沙箱实证:燃气管包死被正确警告")
    print()

    # 测试 4:合理方案
    print("--- 测试 4:合理方案(无任何问题) ---")
    layout4 = {
        "demolish_walls": ["次卧与客厅之间非承重墙"],
        "bedroom_door_direction": "西",
        "bathroom_door_direction": "东",
        "kitchen_cabinet": {"encase_gas_pipe": False, "检修口": True},
        "dining_table": {"clearance_cm": 100},
    }
    passed, errors = check_layout(layout4)
    print(f"  通过: {passed}")
    print(f"  错误: {errors}")
    if passed:
        print("  ✅ 沙箱实证:合理方案通过")
    print()

    # 测试 5:卫生间改位置
    print("--- 测试 5:卫生间改位置 ---")
    layout5 = {"relocate_bathroom": True}
    passed, errors = check_layout(layout5)
    print(f"  错误: {errors}")
    if errors and "沉箱" in errors[0]:
        print("  ✅ 沙箱实证:卫生间改位置被正确警告")
