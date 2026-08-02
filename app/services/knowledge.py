"""
知识库 V0.1 (2026-06-13,V1.0 简化版)

项目书 Day 4 必交付。V0.1 用 JSON 存,等 V1.5 真接 RAG 时升级到 pgvector。

知识库分类(项目书原话,共 100 条):
1. 沈阳装修价格基准 (20 条)
2. 沈阳装修流程与规定 (15 条)
3. 沈阳主流建材市场与价格 (15 条)
4. 沈阳装修避坑指南 (20 条)
5. 沈阳装修风格流行趋势 (15 条)
6. 装修常见问题解答 (15 条)

V0.1 先做 20 条覆盖前 4 类,V1.5 补到 100 条。
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("knowledge")

DATA_FILE = Path(__file__).parent.parent.parent / "data" / "knowledge.json"


def _load_kb() -> list[dict]:
    """读知识库(每次重读,允许热加载)"""
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def search(query: str, top_k: int = 3) -> list[dict]:
    """
    简单关键词搜索 V0.1
    - 不分词(中文不切)
    - 用 substring 匹配 question + answer
    - 命中次数越多分数越高
    - 返回 top_k 个

    V1.5 升级:用 pgvector 做语义检索
    """
    kb = _load_kb()
    if not kb or not query:
        return []

    # 简单分词:按中文字符 + 关键词
    keywords = set()
    for word in ["沈阳", "半包", "大包", "全包", "全案", "报价", "价格", "装修", "户型", "风格",
                 "水电", "瓦工", "木工", "油漆", "防水", "拆改", "流程", "避坑", "材料", "辅材",
                 "主材", "经济", "中端", "高端", "豪华", "平米", "平方米", "全屋定制", "量房",
                 "装修公司", "设计师", "环保", "甲醛", "工期", "施工", "工艺"]:
        if word in query:
            keywords.add(word)
    # 也保留用户问里的中文字(2字以上)
    for m in re.finditer(r'[\u4e00-\u9fff]{2,}', query):
        keywords.add(m.group())

    scored = []
    for entry in kb:
        score = 0
        haystack = entry.get("question", "") + " " + entry.get("answer", "") + " " + " ".join(entry.get("tags", []))
        for kw in keywords:
            if kw in haystack:
                score += 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])
    return [entry for _, entry in scored[:top_k]]


def format_for_llm(results: list[dict]) -> str:
    """把搜索结果格式化成可注入 LLM 的知识块"""
    if not results:
        return ""
    lines = ["[相关知识库条目 - V0.1 知识库,2026-06-13]"]
    for i, e in enumerate(results, 1):
        lines.append(f"\n## {i}. {e['question']}")
        lines.append(f"分类:{e.get('category', '未分类')}")
        lines.append(f"\n{e['answer']}")
    return "\n".join(lines)


# ============================================================
# 单元测试入口
# ============================================================

if __name__ == "__main__":
    tests = [
        "沈阳 90 平半包大概多少钱?",
        "装修怎么避坑?",
        "沈阳哪里买建材?",
        "水电改造要注意什么?",
    ]
    for q in tests:
        print(f"\n=== Query: {q} ===")
        results = search(q, top_k=2)
        for r in results:
            print(f"  [{r.get('category')}] {r['question'][:50]}")
