#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
parse_floor_plan.py · 户型图文本解析脚本
铁律 L3-8:确定性操作(从文本/JSON 描述 → 结构化)

Author: Mavis
Date: 2026-06-26

输入:用户文字描述户型(如 "89 平三室两厅,主卧 4.2x3.6,客厅 4.5x4.0")
输出:标准化 JSON
"""

import re
from typing import Dict, List, Any, Tuple


# 房间名关键词 → 标准名
ROOM_NAME_MAP = {
    "主卧": "主卧", "卧室": "卧室", "次卧": "次卧", "儿童房": "儿童房", "老人房": "老人房", "书房": "书房",
    "客厅": "客厅", "起居室": "客厅", "餐厅": "餐厅", "饭厅": "餐厅",
    "厨房": "厨房", "卫生间": "卫生间", "厕所": "卫生间", "洗手间": "卫生间",
    "阳台": "阳台", "玄关": "玄关", "门厅": "玄关", "过道": "过道", "走廊": "过道",
}


def parse_room_name(text: str) -> str:
    """解析房间名"""
    for kw, std in ROOM_NAME_MAP.items():
        if kw in text:
            return std
    return "未命名"


def parse_floor_plan_text(text: str) -> Dict[str, Any]:
    """
    解析户型文字描述

    Args:
        text: 户型文字描述

    Returns:
        {
            "area": 89,
            "house_type": "三室两厅",
            "rooms": [{"name": "主卧", "length": 4.2, "width": 3.6, "area": 15.12}],
            "confidence": 0.85
        }
    """
    result = {
        "area": None,
        "house_type": None,
        "rooms": [],
        "confidence": 0.0,
    }

    # 1. 解析面积
    area_match = re.search(r"(\d+)\s*平(方米)?", text)
    if area_match:
        result["area"] = int(area_match.group(1))

    # 2. 解析户型(支持中文数字 + 阿拉伯数字)
    CN_NUM = "一二三四五六七八九十两"
    PATTERN_NUM = f"([0-9{CN_NUM}]+)"
    rooms_match = re.search(rf"{PATTERN_NUM}\s*室", text)
    halls_match = re.search(rf"室\s*{PATTERN_NUM}\s*厅", text)

    def cn_to_int(s: str) -> int:
        """中文数字转 int(只支持 1-10 + 两)"""
        cn_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if s.isdigit():
            return int(s)
        return cn_map.get(s, 0)

    if rooms_match:
        rooms_count = cn_to_int(rooms_match.group(1))
        if halls_match:
            halls_count = cn_to_int(halls_match.group(1))
            result["house_type"] = f"{rooms_count}室{halls_count}厅"
        else:
            result["house_type"] = f"{rooms_count}室1厅"

    # 3. 解析每个房间
    # 模式:房间名(可前有任意内容) 数字x数字
    ROOM_NAMES = "(?:主卧|次卧|儿童房|老人房|书房|客厅|餐厅|厨房|卫生间|阳台|玄关|过道|卧室)"
    room_pattern = re.compile(rf"{ROOM_NAMES}\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)")
    for m in room_pattern.finditer(text):
        full_match = m.group(0)
        name = parse_room_name(full_match[:3])  # 取前 3 字符
        if not name or name == "未命名":
            name = parse_room_name(full_match[:2])
        try:
            length = float(m.group(1))
            width = float(m.group(2))
        except (ValueError, IndexError):
            continue
        room = {
            "name": name,
            "length": length,
            "width": width,
            "area": round(length * width, 2),
        }
        result["rooms"].append(room)

    # 4. 估算总面积(如果没填)
    if not result["area"] and result["rooms"]:
        total = sum(r["area"] for r in result["rooms"])
        result["area"] = round(total * 1.15, 0)  # 加 15% 公摊

    # 5. 估算户型(如果没填)
    if not result["house_type"]:
        bedroom_count = sum(1 for r in result["rooms"] if r["name"] in ["主卧", "次卧", "儿童房", "老人房", "书房", "卧室"])
        result["house_type"] = f"{bedroom_count}室1厅"

    # 6. 置信度
    confidence = 0.0
    if result["area"]:
        confidence += 0.3
    if result["house_type"]:
        confidence += 0.2
    if result["rooms"]:
        confidence += 0.3
        if len(result["rooms"]) >= 3:
            confidence += 0.2
    result["confidence"] = round(confidence, 2)

    return result


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("parse_floor_plan.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:89 平三室两厅完整描述
    print("--- 测试 1:89 平三室两厅 ---")
    text1 = "89 平三室两厅,主卧 4.2x3.6,次卧 3.6x3.0,客厅 4.5x4.0,厨房 3.0x2.5,卫生间 2.5x2.0"
    result = parse_floor_plan_text(text1)
    print(f"  面积: {result['area']}")
    print(f"  户型: {result['house_type']}")
    print(f"  房间数: {len(result['rooms'])}")
    for r in result['rooms']:
        print(f"    {r['name']}: {r['length']}x{r['width']} = {r['area']} 平")
    print(f"  置信度: {result['confidence']}")
    if result["area"] == 89 and result["house_type"] == "3室2厅" and len(result["rooms"]) == 5 and result["confidence"] >= 0.9:
        print("  ✅ 测试 1 通过(完整描述)")
    print()

    # 测试 2:简化描述(只有面积)
    print("--- 测试 2:简化描述(只有面积) ---")
    text2 = "我家 120 平四室两厅"
    result = parse_floor_plan_text(text2)
    print(f"  面积: {result['area']}")
    print(f"  户型: {result['house_type']}")
    print(f"  房间数: {len(result['rooms'])}")
    print(f"  置信度: {result['confidence']}")
    if result["area"] == 120 and result["house_type"] == "4室2厅" and result["confidence"] < 0.7:
        print("  ✅ 测试 2 通过(简化描述,置信度低,需人工确认)")
    print()

    # 测试 3:中文逗号分隔
    print("--- 测试 3:中文标点 ---")
    text3 = "100 平,主卧 5x4,客厅 5x4.5,厨房 3.5x3"
    result = parse_floor_plan_text(text3)
    print(f"  房间数: {len(result['rooms'])}")
    for r in result["rooms"]:
        print(f"    {r['name']}: {r['length']}x{r['width']}")
    if len(result["rooms"]) == 3:
        print("  ✅ 测试 3 通过")
    print()

    # 测试 4:无信息
    print("--- 测试 4:无任何信息 ---")
    text4 = "我家要装修"
    result = parse_floor_plan_text(text4)
    print(f"  结果: {result}")
    if result["area"] is None and result["confidence"] == 0:
        print("  ✅ 测试 4 通过(置信度 0,需人工补全)")
    print()

    # 测试 5:含多种标点
    print("--- 测试 5:含 × 特殊符号 ---")
    text5 = "89 平三室两厅主卧4.2×3.6次卧3.6×3.0客厅4.5×4.0"
    result = parse_floor_plan_text(text5)
    print(f"  房间数: {len(result['rooms'])}")
    for r in result["rooms"]:
        print(f"    {r['name']}: {r['length']}x{r['width']}")
    if len(result["rooms"]) == 3:
        print("  ✅ 测试 5 通过(支持 × 特殊符号)")
