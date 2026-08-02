#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_search.py · 施工问答检索脚本
铁律 L3-8:确定性操作

Author: Mavis
Date: 2026-06-26
"""

import json
import os
from typing import Dict, List, Any
from pathlib import Path


CONFIG_PATH = os.environ.get(
    "ZHISHE_GB_STANDARDS",
    str(Path(__file__).parent.parent / "config" / "gb_standards.json")
)


def load_standards() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {"questions": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def search(question: str, top_n: int = 3) -> List[Dict[str, Any]]:
    """
    关键词检索

    Returns:
        Top N 匹配的问题
    """
    data = load_standards()
    questions = data.get("questions", [])

    # 简单关键词匹配(Phase 4 接向量检索)
    results = []
    for q in questions:
        score = 0
        for kw in q.get("keywords", []):
            if kw in question:
                score += 1
        if score > 0:
            results.append({**q, "match_score": score})

    # 按匹配分降序
    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results[:top_n]


def format_answer(question: str) -> str:
    """格式化回答"""
    matches = search(question)

    if not matches:
        return f"抱歉,知识库暂无关于「{question}」的明确答案。建议:1) 咨询专业监理 2) 参考 GB 国标 3) 拍照咨询装修公司。"

    top = matches[0]
    answer = top.get("answer", "")
    source = top.get("source", "国标")
    return f"【{top.get('category', '')}】{answer}\n\n📚 数据来源:{source}"


# ============== 沙箱自测 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("qa_search.py 沙箱实证")
    print("=" * 60)
    print()

    # 测试 1:防水
    print("--- 测试 1:防水怎么刷? ---")
    answer = format_answer("防水刷几遍?需要做闭水试验吗?")
    print(answer)
    if "防水" in answer and "国标" in answer:
        print("  ✅ 测试 1 通过")
    print()

    # 测试 2:水管试压
    print("--- 测试 2:水管怎么验收?试压标准? ---")
    answer = format_answer("水管试压 0.8MPa 保多久?")
    print(answer)
    if "试压" in answer:
        print("  ✅ 测试 2 通过")
    print()

    # 测试 3:电线分色
    print("--- 测试 3:电线怎么接?火线零线颜色? ---")
    answer = format_answer("电线分色标准是什么?")
    print(answer)
    if "火线" in answer and "零线" in answer:
        print("  ✅ 测试 3 通过")
    print()

    # 测试 4:无匹配
    print("--- 测试 4:无匹配问题(智能马桶) ---")
    answer = format_answer("智能马桶哪个牌子好?")
    print(answer)
    if "暂无" in answer or "建议" in answer:
        print("  ✅ 测试 4 通过")
    print()

    # 测试 5:Top 3 检索
    print("--- 测试 5:Top 3 检索 ---")
    matches = search("防水 闭水 24h", top_n=3)
    print(f"  找到 {len(matches)} 条匹配")
    for m in matches:
        print(f"    [{m['match_score']}] {m['question'][:40]}")
    if len(matches) > 0:
        print("  ✅ 测试 5 通过")
