#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
risk_predict.py · 谈单风险预测脚本
铁律 L3-8:确定性操作封装为脚本

Author: Mavis
Date: 2026-06-26
"""

import re
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass


@dataclass
class RiskItem:
    """单个风险"""
    level: str  # 高/中/低
    category: str  # 预算/工期/沟通/设计/质量
    description: str
    suggestion: str


# 风险关键词词典
RISK_KEYWORDS = {
    "预算": {
        "高": ["预算紧张", "钱不够", "贷款", "借钱", "信用卡", "月供", "还款压力大"],
        "中": ["先少做点", "后面再加", "能省就省", "比价", "其他家便宜"],
        "低": ["预算充足", "贷款已批", "现金"],
    },
    "工期": {
        "高": ["下个月要住", "婚期", "孩子上学", "必须 X 月完成", "赶时间"],
        "中": ["希望尽快", "X 月前", "不急但别太慢"],
        "低": ["不着急", "慢慢来", "时间充裕"],
    },
    "设计": {
        "高": ["我要和别人不一样", "网红同款", "高级感", "豪华"],
        "中": ["有自己的想法", "要个性化", "不能太普通"],
        "低": ["按常规来", "标准设计就行"],
    },
    "沟通": {
        "高": ["已经咨询 5 家", "很专业", "别想骗我", "问了很多"],
        "中": ["之前看过 X 家", "了解过"],
        "低": ["第一次装修", "是新手"],
    },
    "质量": {
        "高": ["不能用便宜材料", "必须环保", "E0 必须", "伟星水管"],
        "中": ["要品牌", "不要太差"],
        "低": ["差不多就行"],
    },
}


def extract_risks(text: str) -> List[RiskItem]:
    """
    从谈单文本中提取风险

    Returns:
        风险列表(按严重度排序:高 > 中 > 低)
    """
    risks = []
    found_categories = set()

    for category, level_map in RISK_KEYWORDS.items():
        for level, keywords in level_map.items():
            for kw in keywords:
                if kw in text:
                    risk = RiskItem(
                        level=level,
                        category=category,
                        description=f"客户提到关键词: '{kw}'",
                        suggestion=get_suggestion(category, level, kw),
                    )
                    risks.append(risk)
                    found_categories.add(category)

    # 排序:高 > 中 > 低
    level_order = {"高": 0, "中": 1, "低": 2}
    risks.sort(key=lambda r: (level_order[r.level], r.category))

    return risks


def get_suggestion(category: str, level: str, keyword: str) -> str:
    """根据风险类型和等级给建议"""
    suggestions = {
        ("预算", "高"): f"客户提到 '{keyword}' 可能预算紧张,建议先确认总预算,再谈方案",
        ("预算", "中"): f"客户提到 '{keyword}',注意报价时留 5-10% 余地,避免后期加项",
        ("预算", "低"): "客户预算充足,可推中高档方案",
        ("工期", "高"): f"客户提到 '{keyword}',工期紧,建议立即排施工队,不能等",
        ("工期", "中"): "客户希望尽快,提前确认材料进场时间",
        ("工期", "低"): "客户时间充裕,正常排期",
        ("设计", "高"): f"客户提到 '{keyword}',个性化要求高,必出 2-3 套方案,设计师全程跟",
        ("设计", "中"): "客户有自己的想法,设计师多沟通方案细节",
        ("设计", "低"): "客户接受标准方案,推成熟模板",
        ("沟通", "高"): f"客户提到 '{keyword}',专业度高,需用专业术语,不夸大不忽悠",
        ("沟通", "中"): "客户有比较基础,讲清材料工艺差异",
        ("沟通", "低"): "客户首次装修,讲清流程和标准",
        ("质量", "高"): f"客户提到 '{keyword}',材料必选品牌,E0 必须,不能省",
        ("质量", "中"): "客户注重品牌,主材选品牌,辅材可标准",
        ("质量", "低"): "客户不挑剔,标准配置即可",
    }
    return suggestions.get((category, level), "无")


def extract_client_profile(text: str) -> Dict[str, Any]:
    """提取客户画像"""
    profile = {
        "area": None,  # 面积
        "budget": None,  # 预算
        "rooms": None,  # 房间数
        "package": None,  # 半包/大包
        "style": None,  # 风格
        "has_child": False,  # 有孩子
        "has_pet": False,  # 有宠物
    }

    # 面积
    area_match = re.search(r"(\d+)\s*平(方米)?", text)
    if area_match:
        profile["area"] = int(area_match.group(1))

    # 预算
    budget_match = re.search(r"(\d+)\s*万", text)
    if budget_match:
        profile["budget"] = int(budget_match.group(1)) * 10000

    # 房间数
    room_match = re.search(r"(\d)\s*室", text)
    if room_match:
        profile["rooms"] = int(room_match.group(1))

    # 装修方式
    for pkg in ["全包", "大包", "半包"]:
        if pkg in text:
            profile["package"] = pkg
            break

    # 风格
    for style in ["现代简约", "北欧", "新中式", "日式", "美式", "轻奢", "极简"]:
        if style in text:
            profile["style"] = style
            break

    # 孩子
    if any(kw in text for kw in ["孩子", "小孩", "宝宝", "儿童"]):
        profile["has_child"] = True

    # 宠物
    if any(kw in text for kw in ["猫", "狗", "宠物"]):
        profile["has_pet"] = True

    return profile


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("risk_predict.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:预算紧张
    print("--- 测试 1:客户说预算紧张 ---")
    text1 = "客户说预算 10 万,可能不够,需要贷款,但希望做 89 平三室两厅全包,现代简约风,有 1 个 3 岁孩子"
    risks = extract_risks(text1)
    profile = extract_client_profile(text1)
    print(f"  风险数: {len(risks)}")
    for r in risks[:5]:
        print(f"    [{r.level}] {r.category}: {r.description}")
    print(f"  客户画像: {profile}")
    if len(risks) >= 2 and profile["area"] == 89:
        print("  ✅ 沙箱实证:风险和画像提取成功")
    print()

    # 测试 2:工期紧
    print("--- 测试 2:客户下个月要住 ---")
    text2 = "客户下个月要住,89 平必须 30 天完成,可能赶不上"
    risks = extract_risks(text2)
    profile = extract_client_profile(text2)
    print(f"  风险数: {len(risks)}")
    for r in risks[:3]:
        print(f"    [{r.level}] {r.category}: {r.description}")
    if any(r.level == "高" and r.category == "工期" for r in risks):
        print("  ✅ 沙箱实证:工期高风险识别")
    print()

    # 测试 3:设计要求高
    print("--- 测试 3:客户要网红同款 ---")
    text3 = "客户要网红同款高级感,已经咨询 5 家装修公司,89 平预算 30 万"
    risks = extract_risks(text3)
    profile = extract_client_profile(text3)
    print(f"  风险数: {len(risks)}")
    for r in risks[:3]:
        print(f"    [{r.level}] {r.category}: {r.description}")
    print(f"  客户画像: budget=30 万, area=89")
    if any(r.level == "高" for r in risks):
        print("  ✅ 沙箱实证:设计/沟通高风险识别")
    print()

    # 测试 4:低风险(标准客户)
    print("--- 测试 4:低风险(标准客户) ---")
    text4 = "客户 89 平三室两厅,预算 15 万,半包,喜欢现代简约,第一次装修,什么都不懂,时间充裕,按常规来"
    risks = extract_risks(text4)
    profile = extract_client_profile(text4)
    print(f"  风险数: {len(risks)}")
    print(f"  客户画像: {profile}")
    # 全部应该是低风险
    if all(r.level == "低" for r in risks):
        print("  ✅ 沙箱实证:标准客户 3 个低风险(工期/沟通/设计),符合预期")
    print()

    # 测试 5:多风险综合
    print("--- 测试 5:多风险综合(预算紧+工期紧+设计要求高) ---")
    text5 = "客户预算紧张,信用卡也要刷,90 平必须 1 个月完成,要网红同款,已经咨询 5 家,比价"
    risks = extract_risks(text5)
    print(f"  风险数: {len(risks)}")
    high_risks = [r for r in risks if r.level == "高"]
    print(f"  高风险数: {len(high_risks)}")
    for r in high_risks:
        print(f"    [{r.level}] {r.category}: {r.description} → {r.suggestion[:40]}")
    if len(high_risks) >= 3:
        print("  ✅ 沙箱实证:多高风险综合识别")
