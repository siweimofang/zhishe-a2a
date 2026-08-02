"""
报价引擎测试(V1.0,2026-06-13)
不调 LLM,只测 quote.estimate / breakdown_estimate / parse_user_intent 的数据准确性

这是 V1.0 验收指标:"用户问装修报价,能出相对靠谱的沈阳本地价格" 的关键防线
"""
from __future__ import annotations

import pytest

from app.services.quote import (
    estimate,
    breakdown_estimate,
    parse_user_intent,
    format_estimate_for_llm,
)


# === estimate() 基础 ===

def test_estimate_halfpack_90_middle():
    """半包中端 90 平:40500-54000 元"""
    est = estimate("半包", "中端", 90)
    assert est is not None
    assert est["package"] == "半包"
    assert est["tier"] == "中端"
    assert est["area"] == 90
    assert est["unit_min"] == 450
    assert est["unit_max"] == 600
    assert est["unit_median"] == 525
    assert est["total_min"] == 40500
    assert est["total_max"] == 54000
    assert est["total_median"] == 47250
    assert "装修公司" in est["承接单位主体"]


def test_estimate_halfpack_90_economy_lowest():
    """半包经济 90 平:最便宜的 350*90=31500"""
    est = estimate("半包", "经济", 90)
    assert est is not None
    assert est["unit_min"] == 350
    assert est["total_min"] == 350 * 90  # 31500


def test_estimate_fullpack_130_high():
    """大包高端 130 平:2000-3500 元/平"""
    est = estimate("大包", "高端", 130)
    assert est is not None
    assert est["unit_min"] == 2000
    assert est["unit_max"] == 3500
    assert est["total_median"] == 2750 * 130  # 357500


def test_estimate_fullpack_130_luxury_max():
    """大包豪华 130 平:上限 5000*130=650000"""
    est = estimate("大包", "豪华", 130)
    assert est is not None
    assert est["unit_max"] == 5000
    assert est["total_max"] == 5000 * 130  # 650000


def test_estimate_fullcase_no_standard_range():
    """全案设计无标准区间,一房一价"""
    est = estimate("全案设计", "豪华", 200)
    assert est is not None
    assert est["unit_min"] is None
    assert est["unit_max"] is None
    assert est["total_median"] is None
    assert "一房一价" in est["note"]


def test_estimate_invalid_package_returns_none():
    """未知装修方式返回 None"""
    est = estimate("清包", "经济", 90)  # 清包已被去除
    assert est is None


def test_estimate_invalid_tier_returns_none():
    """未知档次返回 None"""
    est = estimate("半包", "顶配", 90)  # 顶配不在 4 档里
    assert est is None


# === estimate() 含户型/风格(V2.0 留口子,V1.0 应该接受但不计算) ===

def test_estimate_with_house_type_passes_through():
    """V1.0 接收户型/风格参数但不计算(留给 V2.0 系数)"""
    est = estimate("半包", "中端", 90, house_type="三室两厅", style="新中式")
    assert est is not None
    assert est["house_type"] == "三室两厅"
    assert est["style"] == "新中式"


# === breakdown_estimate() 分项拆解 ===

def test_breakdown_halfpack_47250():
    """半包中端 90 平中位价 47250:人工 55% / 辅材 35% / 管理 10%"""
    bd = breakdown_estimate("半包", "中端", 47250)
    assert abs(bd["人工费"]["amount"] - 47250 * 0.55) < 0.01
    assert abs(bd["辅材费"]["amount"] - 47250 * 0.35) < 0.01
    assert abs(bd["管理费"]["amount"] - 47250 * 0.10) < 0.01


def test_breakdown_fullpack_includes_design_fee():
    """大包分项含设计费 8%"""
    bd = breakdown_estimate("大包", "高端", 357500)
    assert "设计费" in bd
    assert abs(bd["设计费"]["amount"] - 357500 * 0.08) < 0.01


# === parse_user_intent() 用户输入解析 ===

def test_parse_halfpack_90():
    """'我家 90 平,想半包,大概多少钱?' → 半包 + 90"""
    intent = parse_user_intent("我家 90 平,想半包,大概多少钱?")
    assert intent["package"] == "半包"
    assert intent["area"] == 90.0
    assert intent["tier"] is None  # 没指定档次


def test_parse_fullpack_middle_100():
    """'100 平全包,中档,沈阳大概多少?' → 大包(全包=大包别名) + 中端 + 100"""
    intent = parse_user_intent("100 平全包,中档,沈阳大概多少?")
    assert intent["package"] == "大包"  # 全包/大包统一
    assert intent["tier"] == "中端"
    assert intent["area"] == 100.0


def test_parse_luxury_fullpack_130():
    """'130 平米大包豪华档,需要多少预算?' → 大包 + 豪华 + 130"""
    intent = parse_user_intent("130 平米大包豪华档,需要多少预算?")
    assert intent["package"] == "大包"
    assert intent["tier"] == "豪华"
    assert intent["area"] == 130.0


def test_parse_fullcase_200():
    """'我家 200 平想做全案设计' → 全案设计 + 200"""
    intent = parse_user_intent("我家 200 平想做全案设计")
    assert intent["package"] == "全案设计"
    assert intent["area"] == 200.0


def test_parse_no_intent():
    """'今天天气怎么样?' → 什么都解析不到"""
    intent = parse_user_intent("今天天气怎么样?")
    assert intent["package"] is None
    assert intent["tier"] is None
    assert intent["area"] is None


# === format_estimate_for_llm() 注入 LLM 的格式 ===

def test_format_llm_block_contains_quote_data():
    """format 出来的内容必须包含精确数字,让 LLM 看到"""
    est = estimate("半包", "中端", 90)
    text = format_estimate_for_llm(est)
    assert "40500" in text  # total_min
    assert "54000" in text  # total_max
    assert "47250" in text  # total_median
    assert "半包" in text
    assert "中端" in text
    assert "不是合同价" in text  # 明确标注


def test_format_llm_block_fullcase_no_number():
    """全案设计格式化后不应该有具体价格"""
    est = estimate("全案设计", "豪华", 200)
    text = format_estimate_for_llm(est)
    assert "一房一价" in text
    # 不应该出现具体数字(因为没标准区间)
    assert "元/平" not in text
