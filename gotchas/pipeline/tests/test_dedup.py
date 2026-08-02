#!/usr/bin/env python3
"""dedup 单元测试（零依赖）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from annotator import dedup

EXISTING = [
    {"ku_id": "GZ-SY-00003", "title": "水电按米实报实销：施工方绕路虚报米数致费用翻倍",
     "description": "装修公司水电改造按米计费，施工方故意绕路增加米数，导致费用比预估翻倍甚至更多。"},
    {"ku_id": "GZ-SY-00010", "title": "阳台封窗用料陷阱",
     "description": "封阳台时型材壁厚不足、五金件用杂牌，存在安全隐患。"},
]


def test_identical_title_flagged():
    cand = {"title": "水电按米实报实销：施工方绕路虚报米数致费用翻倍", "description": "完全不同的描述内容。"}
    hit = dedup.find_similar(cand, EXISTING)
    assert hit is not None and hit["ku_id"] == "GZ-SY-00003", f"标题相同应命中: {hit}"


def test_similar_description_flagged():
    cand = {"title": "全新标题", "description": "装修公司水电改造按米计费，施工方故意绕路增加米数，导致费用比预估翻倍。"}
    hit = dedup.find_similar(cand, EXISTING)
    assert hit is not None and hit["ku_id"] == "GZ-SY-00003", f"描述高度相似应命中: {hit}"


def test_different_not_flagged():
    cand = {"title": "承重墙绝对不能拆除", "description": "拆除承重墙会导致整栋楼结构受损，是致命级安全隐患。"}
    hit = dedup.find_similar(cand, EXISTING)
    assert hit is None, f"完全不同不应命中: {hit}"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
