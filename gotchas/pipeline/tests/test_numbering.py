#!/usr/bin/env python3
"""numbering + loader 单元测试（零依赖）。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from annotator import validator, loader


def test_next_id_from_empty():
    assert validator.next_ku_id([]) == "GZ-SY-00001"


def test_next_id_increment():
    ids = ["GZ-SY-00001", "GZ-SY-00005", "GZ-SY-00003"]
    assert validator.next_ku_id(ids) == "GZ-SY-00006"


def test_next_id_ignores_malformed():
    ids = ["GZ-SY-00010", "BAD-ID", "", None]
    assert validator.next_ku_id(ids) == "GZ-SY-00011"


def test_loader_split_by_separator():
    text = "第一条经验，足够长的内容用于测试。\n---\n第二条经验，也足够长。\n---\n第三条经验，同样足够长。"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = Path(f.name)
    result = loader.load_material(path, min_len=5)
    assert len(result["segments"]) == 3, f"应切出3段: {result['segments']}"
    path.unlink()


def test_loader_no_separator_single():
    text = "没有分隔符的一整段经验文本，足够长。"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = Path(f.name)
    result = loader.load_material(path, min_len=5)
    assert len(result["segments"]) == 1, "无分隔符应整体为1段"
    path.unlink()


def test_loader_skips_short():
    text = "这条够长可以保留下来。\n---\n短"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = Path(f.name)
    result = loader.load_material(path, min_len=5)
    assert len(result["segments"]) == 1 and len(result["skipped_short"]) == 1
    path.unlink()


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
