#!/usr/bin/env python3
"""validator 单元测试（零依赖，python tests/test_validator.py 直接跑）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from annotator import validator


def _valid_candidate():
    return {
        "title": "瓷砖空鼓率超标必须返工",
        "stage": "STAGE_04",
        "role": ["ROLE_OWNER", "ROLE_CONTRACTOR"],
        "severity": "SEV_HIGH",
        "problem_type": ["TYPE_QUALITY"],
        "trade": ["TRADE_TILE"],
        "material": ["MAT_TILE"],
        "scope": "universal",
        "description": "瓦工铺贴瓷砖时水泥砂浆配比不当或基层未处理，导致瓷砖与墙面之间形成空腔。"
                       "空鼓率超过国标5%时，瓷砖后期极易脱落砸伤人或物，必须返工重铺。",
        "typical_scenario": "沈阳某业主卫生间墙砖铺贴半年后大面积空鼓，敲之咚咚响，最终整面墙返工。",
        "how_to_avoid": "1. 铺贴前基层必须拉毛并湿润。2. 水泥砂浆配比按规范。3. 验收用空鼓锤逐块敲击，"
                        "空鼓率超5%要求返工。4. 大板瓷砖必须用瓷砖胶薄贴法。",
        "evidence": {
            "source_type": "expert_opinion",
            "source_ref": "设计师实战经验",
            "frequency": "高频(30-60%)",
            "confidence": "中(单源可靠)",
        },
    }


def test_valid_passes():
    errors = validator.validate_candidate(_valid_candidate())
    assert errors == [], f"合法候选不应有错误，实际: {errors}"


def test_missing_field():
    cand = _valid_candidate()
    del cand["how_to_avoid"]
    errors = validator.validate_candidate(cand)
    assert any(e.startswith("missing:how_to_avoid") for e in errors), f"应报缺字段: {errors}"


def test_bad_enum():
    cand = _valid_candidate()
    cand["stage"] = "STAGE_99"
    errors = validator.validate_candidate(cand)
    assert any("enum:stage" in e for e in errors), f"应报枚举越界: {errors}"


def test_bad_role_enum():
    cand = _valid_candidate()
    cand["role"] = ["ROLE_ALIEN"]
    errors = validator.validate_candidate(cand)
    assert any("enum:role" in e for e in errors), f"应报role枚举越界: {errors}"


def test_too_short_description():
    cand = _valid_candidate()
    cand["description"] = "太短了。"
    errors = validator.validate_candidate(cand)
    assert any("too_short:description" in e for e in errors), f"应报过短: {errors}"


def test_too_long_description():
    cand = _valid_candidate()
    cand["description"] = "字" * 501
    errors = validator.validate_candidate(cand)
    assert any("too_long:description" in e for e in errors), f"应报过长: {errors}"


def test_enrich_adds_metadata():
    ku = validator.enrich(_valid_candidate(), "GZ-SY-00099")
    assert ku["ku_id"] == "GZ-SY-00099"
    assert ku["metadata"]["quality_level"] == "DRAFT"
    assert ku["metadata"]["verified"] is False
    assert ku["metadata"]["created_by"] == "ai"


def test_single_value_role_normalized():
    cand = _valid_candidate()
    cand["role"] = "ROLE_OWNER"  # 单值而非数组
    errors = validator.validate_candidate(cand)
    assert errors == [], f"单值role应被容错: {errors}"
    ku = validator.enrich(cand, "GZ-SY-00100")
    assert ku["role"] == ["ROLE_OWNER"], "应规范化为列表"


def test_coerce_enum_with_label():
    cand = _valid_candidate()
    cand["stage"] = "STAGE_04施工阶段"      # 模型把中文标签一起吐出
    cand["trade"] = ["TRADE_TILE瓦工瓷砖"]
    errors = validator.validate_candidate(cand)
    assert errors == [], f"带标签枚举应被纠偏后通过: {errors}"
    assert cand["stage"] == "STAGE_04", f"stage应还原: {cand['stage']}"
    assert cand["trade"] == ["TRADE_TILE"], f"trade应还原: {cand['trade']}"


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
