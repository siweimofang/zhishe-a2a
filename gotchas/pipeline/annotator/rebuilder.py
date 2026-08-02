"""
索引重建层：审核通过的 KU 合并进 all_ku.json 后，
重建 by_stage / by_severity 分片文件，并重算 stats.json。

写入前自动备份 all_ku.json 到 pipeline/backup/（风险回滚）。
"""
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import List

from . import config


def _load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_all_ku(all_ku_path: Path = config.ALL_KU_PATH) -> Path:
    """备份 all_ku.json，返回备份路径。"""
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = config.BACKUP_DIR / f"all_ku_{stamp}.json"
    if all_ku_path.exists():
        shutil.copy2(all_ku_path, backup)
    return backup


def load_all_kus(all_ku_path: Path = config.ALL_KU_PATH) -> List[dict]:
    return _load_json(all_ku_path, [])


def merge_kus(new_kus: List[dict], all_ku_path: Path = config.ALL_KU_PATH) -> List[dict]:
    """
    把新 KU 合并进 all_ku.json（按 ku_id 去重，新值覆盖旧值）。
    返回合并后的完整列表（已写盘）。
    """
    existing = load_all_kus(all_ku_path)
    index = {ku.get("ku_id"): ku for ku in existing if ku.get("ku_id")}
    for ku in new_kus:
        kid = ku.get("ku_id")
        if kid:
            index[kid] = ku
    merged = list(index.values())
    # 按编号排序，保持稳定
    merged.sort(key=lambda k: k.get("ku_id", ""))
    _dump_json(all_ku_path, merged)
    return merged


def _stage_name_map() -> dict:
    tax = _load_json(config.TAXONOMY_PATH, {})
    return {
        code: info.get("name", code)
        for code, info in tax.get("stage", {}).get("values", {}).items()
    }


def rebuild_by_stage(all_kus: List[dict]) -> None:
    """重建 by_stage/stage_0X_名称.json 分片。"""
    name_map = _stage_name_map()
    buckets: dict = {}
    for ku in all_kus:
        s = ku.get("stage", "")
        buckets.setdefault(s, []).append(ku)

    # 清理旧分片
    if config.BY_STAGE_DIR.exists():
        for old in config.BY_STAGE_DIR.glob("stage_*.json"):
            old.unlink()

    for stage, kus in buckets.items():
        # stage 形如 STAGE_03 -> 03
        num = stage.split("_")[-1] if "_" in stage else "00"
        name = name_map.get(stage, stage)
        fname = f"stage_{num}_{name}.json"
        _dump_json(config.BY_STAGE_DIR / fname, kus)


def rebuild_by_severity(all_kus: List[dict]) -> None:
    """重建 by_severity/sev_xxx.json 分片（文件名小写）。"""
    sev_file = {
        "SEV_CRITICAL": "sev_critical.json",
        "SEV_HIGH": "sev_high.json",
        "SEV_MEDIUM": "sev_medium.json",
        "SEV_LOW": "sev_low.json",
    }
    buckets = {k: [] for k in sev_file}
    for ku in all_kus:
        sv = ku.get("severity", "")
        if sv in buckets:
            buckets[sv].append(ku)

    if config.BY_SEVERITY_DIR.exists():
        for old in config.BY_SEVERITY_DIR.glob("sev_*.json"):
            old.unlink()

    for sv, fname in sev_file.items():
        _dump_json(config.BY_SEVERITY_DIR / fname, buckets[sv])


def rebuild_stats(all_kus: List[dict]) -> dict:
    """重算 stats.json（沿用现有结构）。"""
    relations = _load_json(config.RELATIONS_PATH, [])

    def count(key, multi=False):
        m = {}
        for ku in all_kus:
            v = ku.get(key)
            if multi:
                for item in (v or []):
                    m[item] = m.get(item, 0) + 1
            else:
                if v is None:
                    continue
                m[v] = m.get(v, 0) + 1
        return dict(sorted(m.items()))

    quality = {}
    for ku in all_kus:
        ql = ku.get("metadata", {}).get("quality_level", "UNKNOWN")
        quality[ql] = quality.get(ql, 0) + 1

    reliable_plus = sum(
        1 for ku in all_kus
        if ku.get("metadata", {}).get("quality_level") in ("RELIABLE", "CERTIFIED")
    )

    stage_cov = {ku.get("stage") for ku in all_kus if ku.get("stage")}
    trade_cov = set()
    for ku in all_kus:
        for t in ku.get("trade", []) or []:
            trade_cov.add(t)
    all_stages = {f"STAGE_0{i}" for i in range(1, 9)}
    all_trades = {
        "TRADE_DESIGN", "TRADE_DEMOLISH", "TRADE_PLUMBING", "TRADE_WATERPROOF",
        "TRADE_TILE", "TRADE_CARPENTRY", "TRADE_PAINT", "TRADE_CABINET",
        "TRADE_DOOR", "TRADE_FLOOR", "TRADE_BATHROOM", "TRADE_ELECTRICAL",
    }

    stats = {
        "version": "1.1",
        "total_kus": len(all_kus),
        "total_relations": len(relations),
        "by_stage": count("stage"),
        "by_severity": count("severity"),
        "by_scope": count("scope"),
        "by_role": count("role", multi=True),
        "by_trade": count("trade", multi=True),
        "by_material": count("material", multi=True),
        "quality_levels": dict(sorted(quality.items())),
        "coverage": {
            "stages_covered": f"{len(stage_cov)}/8",
            "trades_covered": f"{len(trade_cov)}/12",
            "empty_stages": sorted(all_stages - stage_cov),
            "empty_trades": sorted(all_trades - trade_cov),
        },
        "phase1_target": {
            "original": 10000,
            "revised": "200-300 RELIABLE+",
            "current_reliable_plus": reliable_plus,
            "note": "Phase 1目标从1万条校准为200-300条高质量(RELIABLE/CERTIFIED)KU",
        },
        "last_updated": date.today().isoformat(),
    }
    _dump_json(config.STATS_PATH, stats)
    return stats


def full_rebuild(all_ku_path: Path = config.ALL_KU_PATH) -> dict:
    """读取当前 all_ku.json，重建所有分片与统计。返回 stats。"""
    all_kus = load_all_kus(all_ku_path)
    rebuild_by_stage(all_kus)
    rebuild_by_severity(all_kus)
    return rebuild_stats(all_kus)
