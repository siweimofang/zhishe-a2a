"""
校验层：schema 结构校验 + 枚举校验 + 自动编号 + 自动打标。

零第三方依赖：直接读 ku_schema_v1.json 的 required 与 taxonomy_v1.json 的枚举，
手写校验逻辑（不依赖 jsonschema 库）。
"""
import json
import re
from datetime import date
from pathlib import Path
from typing import List, Tuple

from . import config

KU_ID_PATTERN = re.compile(r"^GZ-SY-\d{4,6}$")

# schema required 字段（与 ku_schema_v1.json 一致）
REQUIRED_FIELDS = [
    "ku_id", "title", "stage", "role", "severity", "description", "how_to_avoid",
]


class EnumSets:
    """从 taxonomy_v1.json 加载的全部枚举白名单。"""

    def __init__(self, taxonomy_path: Path = config.TAXONOMY_PATH):
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            tax = json.load(f)

        def values(key):
            return set(tax.get(key, {}).get("values", {}).keys())

        self.stage = values("stage")
        self.role = values("role")
        self.severity = values("severity")
        self.problem_type = values("problem_type")
        self.trade = values("trade")
        self.material = values("material")
        self.scope = values("scope")
        self.source_type = values("evidence_source_type")
        self.confidence = values("evidence_confidence")
        self.frequency = values("evidence_frequency")


_enums_cache = None


def get_enums() -> EnumSets:
    global _enums_cache
    if _enums_cache is None:
        _enums_cache = EnumSets()
    return _enums_cache


def _as_list(value) -> list:
    """容错：把单值包成列表，None 转空列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _coerce_single(value, enumset):
    """把 'STAGE_04施工阶段' 这类带标签的值还原为标准枚举码（前缀匹配）。"""
    if not isinstance(value, str):
        return value
    if value in enumset:
        return value
    for member in enumset:
        if value.startswith(member):
            return member
    return value


def _coerce_list(values, enumset):
    return [_coerce_single(v, enumset) for v in _as_list(values)]


def coerce_enums(candidate: dict, enums: EnumSets = None) -> dict:
    """
    枚举纠偏：模型常把枚举值连同中文标签一起输出（如 'STAGE_04施工阶段'），
    这里用前缀匹配还原成标准枚举码，提升抽取鲁棒性。原地修改并返回 candidate。
    """
    if enums is None:
        enums = get_enums()
    if not isinstance(candidate, dict):
        return candidate

    for field in ["stage", "severity", "scope"]:
        if field in candidate:
            candidate[field] = _coerce_single(candidate[field], getattr(enums, field))

    candidate["role"] = _coerce_list(candidate.get("role"), enums.role)
    for field, enumset in [
        ("problem_type", enums.problem_type),
        ("trade", enums.trade),
        ("material", enums.material),
    ]:
        if field in candidate and candidate[field] is not None:
            candidate[field] = _coerce_list(candidate[field], enumset)

    evidence = candidate.get("evidence")
    if isinstance(evidence, dict):
        if "source_type" in evidence:
            evidence["source_type"] = _coerce_single(evidence["source_type"], enums.source_type)
        if "confidence" in evidence:
            evidence["confidence"] = _coerce_single(evidence["confidence"], enums.confidence)
        if "frequency" in evidence:
            evidence["frequency"] = _coerce_single(evidence["frequency"], enums.frequency)
    return candidate


def validate_candidate(candidate: dict, enums: EnumSets = None) -> List[str]:
    """
    校验一条候选 KU（不含 ku_id/metadata，由 enrich 补）。

    返回错误信息列表；空列表表示通过。
    错误类型前缀：missing / enum / too_short / too_long / type。
    校验前会先做枚举纠偏（容忍模型输出 'STAGE_04施工阶段' 这类带标签的值）。
    """
    if enums is None:
        enums = get_enums()
    errors: List[str] = []

    if not isinstance(candidate, dict):
        return ["type:候选不是 JSON 对象"]

    # 先纠偏，把 'STAGE_04施工阶段' 还原成 'STAGE_04'
    coerce_enums(candidate, enums)

    # ── 必填内容字段（ku_id 由 enrich 补，这里不查）──
    for field in ["title", "stage", "role", "severity", "description", "how_to_avoid"]:
        if field not in candidate or candidate.get(field) in (None, "", []):
            errors.append(f"missing:{field}")

    # ── 单选枚举 ──
    if candidate.get("stage") and candidate["stage"] not in enums.stage:
        errors.append(f"enum:stage={candidate['stage']}")
    if candidate.get("severity") and candidate["severity"] not in enums.severity:
        errors.append(f"enum:severity={candidate['severity']}")
    if candidate.get("scope") and candidate["scope"] not in enums.scope:
        errors.append(f"enum:scope={candidate['scope']}")

    # ── 多选枚举 ──
    for field, enumset in [
        ("role", enums.role),
        ("problem_type", enums.problem_type),
        ("trade", enums.trade),
        ("material", enums.material),
    ]:
        if field in candidate and candidate[field] is not None:
            items = _as_list(candidate[field])
            for item in items:
                if item not in enumset:
                    errors.append(f"enum:{field}={item}")
    # role 至少一个
    if not _as_list(candidate.get("role")):
        errors.append("missing:role(至少一个)")

    # ── 长度约束 ──
    title = candidate.get("title", "")
    if title and len(title) > 80:
        errors.append("too_long:title>80")

    for field in ["description", "how_to_avoid"]:
        val = candidate.get(field, "")
        if val:
            if len(val) < config.MIN_FIELD_LEN:
                errors.append(f"too_short:{field}<{config.MIN_FIELD_LEN}")
            if len(val) > config.MAX_FIELD_LEN:
                errors.append(f"too_long:{field}>{config.MAX_FIELD_LEN}")

    scenario = candidate.get("typical_scenario", "")
    if scenario and len(scenario) > 300:
        errors.append("too_long:typical_scenario>300")

    # ── evidence 子字段枚举 ──
    evidence = candidate.get("evidence")
    if isinstance(evidence, dict):
        st = evidence.get("source_type")
        if st and st not in enums.source_type:
            errors.append(f"enum:evidence.source_type={st}")
        conf = evidence.get("confidence")
        if conf and conf not in enums.confidence:
            errors.append(f"enum:evidence.confidence={conf}")
        freq = evidence.get("frequency")
        if freq and freq not in enums.frequency:
            errors.append(f"enum:evidence.frequency={freq}")

    return errors


def normalize(candidate: dict) -> dict:
    """把数组字段统一成 list，去掉 None 值字段，便于落库格式整齐。"""
    out = dict(candidate)
    for field in ["role", "problem_type", "trade", "material", "related_ku_ids"]:
        if field in out:
            out[field] = _as_list(out[field])
    # material 缺省补空列表（schema 允许空数组）
    if "material" not in out:
        out["material"] = []
    return out


def next_ku_id(existing_ids: List[str]) -> str:
    """根据现有编号列表，返回下一个可用 GZ-SY-XXXXX（5 位补零）。"""
    max_n = 0
    for kid in existing_ids:
        m = KU_ID_PATTERN.match(kid or "")
        if m:
            n = int(kid.split("-")[-1])
            if n > max_n:
                max_n = n
    return f"GZ-SY-{max_n + 1:05d}"


def load_existing_ids(all_ku_path: Path = config.ALL_KU_PATH) -> List[str]:
    """读取现有库的全部 ku_id。"""
    if not all_ku_path.exists():
        return []
    with open(all_ku_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [ku.get("ku_id", "") for ku in data]


def enrich(candidate: dict, ku_id: str, source_file: str = "pipeline") -> dict:
    """
    给校验通过的候选补上 ku_id 与 metadata，产出完整 KU（符合 schema 字段集）。
    quality_level=DRAFT、verified=false、created_by=ai（spec 决策）。
    """
    today = date.today().isoformat()
    ku = normalize(candidate)
    ku["ku_id"] = ku_id

    # 补齐 schema 中常见可选字段缺省
    ku.setdefault("scope", "universal")
    ku.setdefault("related_ku_ids", [])

    metadata = {
        "created_at": today,
        "updated_at": today,
        "created_by": "ai",
        "verified": False,
        "verify_method": "not_verified",
        "version": "1.0",
        "source_file": source_file,
        "quality_level": "DRAFT",
        "expires_at": None,
        "last_reviewed_at": None,
    }
    ku["metadata"] = metadata
    return ku


def validate_and_enrich(
    candidate: dict, ku_id: str, enums: EnumSets = None, source_file: str = "pipeline"
) -> Tuple[dict, List[str]]:
    """校验 + 打标的便捷封装。返回 (enriched_ku 或 None, errors)。"""
    errors = validate_candidate(candidate, enums)
    if errors:
        return None, errors
    return enrich(candidate, ku_id, source_file), []
