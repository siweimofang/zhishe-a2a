#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
case_match.py · 案例匹配度计算脚本
铁律 L3-8:确定性操作 + L3 原则 5 维加权

Author: Mavis
Date: 2026-06-26

5 维加权:
- 城市匹配(20%)
- 面积匹配(20%)
- 风格匹配(25%)
- 档次匹配(15%)
- 户型匹配(20%)
"""

from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field


# 沈阳赫慕空间设计 6 位设计师(沙箱实证)
DESIGNERS = [
    {
        "id": "designer_li",
        "name": "李工",
        "specialty": "现代简约",
        "city": "沈阳",
        "years": 12,
        "cases": 89,
        "price_range": "中端-中高档",
        "style_score": {"现代简约": 95, "北欧": 85, "极简": 90, "新中式": 70, "日式": 75},
        "area_range": [60, 200],
        "communication": "理性型,讲数据讲工艺",
    },
    {
        "id": "designer_wang",
        "name": "王工",
        "specialty": "北欧",
        "city": "沈阳",
        "years": 8,
        "cases": 56,
        "price_range": "经济-中端",
        "style_score": {"北欧": 95, "日式": 88, "极简": 85, "现代简约": 80, "新中式": 65},
        "area_range": [40, 150],
        "communication": "温和型,讲故事讲生活",
    },
    {
        "id": "designer_zhang",
        "name": "张工",
        "specialty": "新中式",
        "city": "沈阳",
        "years": 15,
        "cases": 120,
        "price_range": "中高档-豪华",
        "style_score": {"新中式": 98, "中式": 95, "日式": 80, "现代简约": 70, "北欧": 60},
        "area_range": [80, 300],
        "communication": "专业型,讲文化讲设计",
    },
    {
        "id": "designer_liu",
        "name": "刘工",
        "specialty": "轻奢",
        "city": "沈阳",
        "years": 10,
        "cases": 75,
        "price_range": "中高档",
        "style_score": {"轻奢": 95, "现代简约": 85, "极简": 88, "新中式": 75, "北欧": 70},
        "area_range": [70, 250],
        "communication": "细致型,讲细节讲品质",
    },
    {
        "id": "designer_chen",
        "name": "陈工",
        "specialty": "日式",
        "city": "沈阳",
        "years": 7,
        "cases": 42,
        "price_range": "经济-中端",
        "style_score": {"日式": 95, "北欧": 80, "极简": 90, "现代简约": 75, "新中式": 70},
        "area_range": [40, 130],
        "communication": "细致型,讲收纳讲细节",
    },
    {
        "id": "designer_zhao",
        "name": "赵工",
        "specialty": "美式",
        "city": "沈阳",
        "years": 9,
        "cases": 50,
        "price_range": "中端-中高档",
        "style_score": {"美式": 95, "现代简约": 70, "新中式": 65, "北欧": 60, "极简": 55},
        "area_range": [90, 280],
        "communication": "热情型,讲氛围讲情调",
    },
]

# 权重
WEIGHTS = {
    "city": 0.20,
    "area": 0.20,
    "style": 0.25,
    "tier": 0.15,
    "rooms": 0.20,
}


def city_score(user_city: str, designer_city: str) -> float:
    """城市匹配分(0-100)"""
    if user_city == designer_city:
        return 100
    # 同省 80 分
    user_provinces = {"沈阳": "辽宁", "大连": "辽宁", "长春": "吉林", "哈尔滨": "黑龙江",
                     "北京": "北京", "上海": "上海", "广州": "广东", "深圳": "广东",
                     "杭州": "浙江", "成都": "四川", "南京": "江苏", "武汉": "湖北",
                     "西安": "陕西"}
    p1 = user_provinces.get(user_city, "")
    p2 = user_provinces.get(designer_city, "")
    if p1 and p1 == p2:
        return 80
    return 50  # 外省


def area_score(user_area: float, designer_range: List[int]) -> float:
    """面积匹配分(0-100,差距越小分越高)"""
    low, high = designer_range
    if low <= user_area <= high:
        # 在范围内,越接近中间越高
        mid = (low + high) / 2
        diff = abs(user_area - mid) / (high - low)
        return int(100 - diff * 30)  # 100-70 分
    # 超出范围,差距越大分越低
    if user_area < low:
        diff = (low - user_area) / low
        return max(0, int(80 - diff * 80))
    diff = (user_area - high) / high
    return max(0, int(80 - diff * 80))


def style_score(user_style: str, designer_styles: Dict[str, int]) -> float:
    """风格匹配分(0-100)"""
    if not user_style:
        return 70  # 用户没填,给 70 中性分
    return designer_styles.get(user_style, 50)


def tier_score(user_tier: str, designer_price_range: str) -> float:
    """档次匹配分(0-100)"""
    if not user_tier:
        return 70
    # 简单匹配:user_tier 在 designer_price_range 中
    return 100 if user_tier in designer_price_range else 60


def rooms_score(user_rooms: int, designer_rooms_avg: int = 5) -> float:
    """户型匹配分(简化,设计师接待各户型)"""
    return 90  # 沈阳赫慕接所有户型


def match_designer(user: Dict[str, Any], designer: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """
    计算用户和设计师的匹配分

    Args:
        user: {city, area, style, tier, rooms}
        designer: 设计师配置

    Returns:
        (总分, 分项得分 dict)
    """
    city = city_score(user.get("city", ""), designer["city"])
    area = area_score(user.get("area", 89), designer["area_range"])
    style = style_score(user.get("style", ""), designer["style_score"])
    tier = tier_score(user.get("tier", ""), designer["price_range"])
    rooms = rooms_score(user.get("rooms", 5))

    scores = {
        "city": city,
        "area": area,
        "style": style,
        "tier": tier,
        "rooms": rooms,
    }
    total = sum(scores[k] * WEIGHTS[k] for k in scores)

    return total, scores


def top_3_match(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    返回 Top 3 匹配设计师(按总分降序)
    """
    results = []
    for d in DESIGNERS:
        score, breakdown = match_designer(user, d)
        results.append({
            "designer_id": d["id"],
            "designer_name": d["name"],
            "specialty": d["specialty"],
            "total_score": round(score, 1),
            "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
            "years": d["years"],
            "cases": d["cases"],
            "communication": d["communication"],
        })

    results.sort(key=lambda r: r["total_score"], reverse=True)
    return results[:3]


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("case_match.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:沈阳 89 平现代简约中端
    print("--- 测试 1:沈阳 89 平现代简约中端 ---")
    user1 = {"city": "沈阳", "area": 89, "style": "现代简约", "tier": "中端", "rooms": 3}
    top3 = top_3_match(user1)
    for i, d in enumerate(top3, 1):
        print(f"  #{i} {d['designer_name']}({d['specialty']}) 总分 {d['total_score']}")
        for k, v in d["breakdown"].items():
            print(f"     {k}: {v}")
    if top3[0]["designer_id"] == "designer_li":
        print("  ✅ 沙箱实证:沈阳现代简约首选李工(95 分)")
    print()

    # 测试 2:沈阳 89 平北欧
    print("--- 测试 2:沈阳 89 平北欧 ---")
    user2 = {"city": "沈阳", "area": 89, "style": "北欧", "tier": "中端", "rooms": 3}
    top3 = top_3_match(user2)
    for i, d in enumerate(top3, 1):
        print(f"  #{i} {d['designer_name']}({d['specialty']}) 总分 {d['total_score']}")
    if top3[0]["designer_id"] == "designer_wang":
        print("  ✅ 沙箱实证:沈阳北欧首选王工")
    print()

    # 测试 3:沈阳 200 平新中式豪华
    print("--- 测试 3:沈阳 200 平新中式豪华 ---")
    user3 = {"city": "沈阳", "area": 200, "style": "新中式", "tier": "豪华", "rooms": 4}
    top3 = top_3_match(user3)
    for i, d in enumerate(top3, 1):
        print(f"  #{i} {d['designer_name']}({d['specialty']}) 总分 {d['total_score']}")
    if top3[0]["designer_id"] == "designer_zhang":
        print("  ✅ 沙箱实证:沈阳新中式豪华首选张工(15 年 120 案例)")
    print()

    # 测试 4:北京 100 平现代简约
    print("--- 测试 4:北京 100 平现代简约(外省降分) ---")
    user4 = {"city": "北京", "area": 100, "style": "现代简约", "tier": "中端", "rooms": 3}
    top3 = top_3_match(user4)
    for i, d in enumerate(top3, 1):
        print(f"  #{i} {d['designer_name']} 总分 {d['total_score']}")
    # 沈阳赫慕 6 位都在沈阳,北京客户会得分偏低
    if top3[0]["total_score"] < 85:
        print("  ✅ 沙箱实证:外省客户降分(沈阳赫慕本地服务)")
    print()

    # 测试 5:沈阳 80 平日式
    print("--- 测试 5:沈阳 80 平日式 ---")
    user5 = {"city": "沈阳", "area": 80, "style": "日式", "tier": "中端", "rooms": 2}
    top3 = top_3_match(user5)
    for i, d in enumerate(top3, 1):
        print(f"  #{i} {d['designer_name']}({d['specialty']}) 总分 {d['total_score']}")
    if top3[0]["designer_id"] == "designer_chen":
        print("  ✅ 沙箱实证:沈阳日式首选陈工")
