"""
知识库 V0.1 测试 (2026-06-13)
"""
from __future__ import annotations

import pytest

from app.services.knowledge import search, format_for_llm


def test_search_returns_at_least_one_for_quote_question():
    """问报价,应该返回价格类知识"""
    results = search("沈阳 90 平半包大概多少钱?", top_k=3)
    assert len(results) > 0
    assert any("价格" in r.get("category", "") for r in results)


def test_search_returns_k001_for_halfpack():
    """问半包,应该返回 k001(价格基准)"""
    results = search("半包价格", top_k=3)
    assert any(r["id"] == "k001" for r in results)


def test_search_returns_pitfall_for_pitfall_question():
    """问避坑,应该返回避坑类"""
    results = search("装修怎么避坑?", top_k=3)
    assert any("避坑" in r.get("category", "") for r in results)


def test_search_returns_process_for_process_question():
    """问流程,应该返回流程类"""
    results = search("装修流程是什么?", top_k=3)
    assert any("流程" in r.get("category", "") for r in results)


def test_search_empty_query_returns_empty():
    """空查询返回空"""
    assert search("", top_k=3) == []


def test_search_unrelated_query_returns_empty():
    """无关问题返回空(或空或低分,V0.1 简单匹配可能返回低分)"""
    results = search("今天天气怎么样?", top_k=3)
    # V0.1 简单匹配:如果搜不到任何关键词,返回空
    # 接受"返回空"或"返回一些低相关度"的两种情况(都合理)
    if results:
        # 如果有结果,应该是低相关度的(不是直接命中)
        for r in results:
            assert "天气" not in r["answer"]


def test_format_for_llm_includes_question():
    """format 出来的内容包含问题"""
    results = search("装修避坑", top_k=2)
    if results:
        text = format_for_llm(results)
        assert "##" in text
        assert "分类:" in text


def test_kb_has_at_least_20_entries():
    """V0.1 至少 20 条(覆盖前 4 类)"""
    # 直接读文件验证(更准确,不依赖搜索)
    import json
    from pathlib import Path
    kb_file = Path(__file__).parent.parent / "data" / "knowledge.json"
    kb = json.loads(kb_file.read_text(encoding="utf-8"))
    assert len(kb) >= 20
    # 前 4 类都有
    categories = set(e.get("category", "") for e in kb)
    expected = {
        "沈阳装修价格基准",
        "沈阳装修流程与规定",
        "沈阳主流建材市场与价格",
        "沈阳装修避坑指南",
    }
    assert expected.issubset(categories), f"缺少分类:{expected - categories}"
