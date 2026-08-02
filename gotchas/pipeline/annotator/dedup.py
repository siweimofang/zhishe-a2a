"""
去重层：候选 KU 与现有库做标题/描述相似度比对，标记疑似重复。

零第三方依赖，用标准库 difflib.SequenceMatcher。
阈值（spec 已确认）：标题 >=0.8 或 描述 >=0.7 判为疑似重复。
只标记、不自动丢弃，交人工裁决。
"""
import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional

from . import config


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def load_existing_kus(all_ku_path: Path = config.ALL_KU_PATH) -> List[dict]:
    if not all_ku_path.exists():
        return []
    with open(all_ku_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_similar(
    candidate: dict,
    existing: List[dict],
    title_threshold: float = config.DEDUP_TITLE_THRESHOLD,
    desc_threshold: float = config.DEDUP_DESC_THRESHOLD,
) -> Optional[dict]:
    """
    在现有库中找与候选最相似的一条。

    返回 None 表示无疑似重复；否则返回
        {"ku_id":..., "title":..., "title_ratio":float, "desc_ratio":float, "reason":str}
    """
    c_title = candidate.get("title", "")
    c_desc = candidate.get("description", "")

    best = None
    for ku in existing:
        t_ratio = _ratio(c_title, ku.get("title", ""))
        d_ratio = _ratio(c_desc, ku.get("description", ""))
        is_dup = t_ratio >= title_threshold or d_ratio >= desc_threshold
        score = max(t_ratio, d_ratio)
        if is_dup and (best is None or score > best["_score"]):
            reason = []
            if t_ratio >= title_threshold:
                reason.append(f"标题相似{t_ratio:.2f}")
            if d_ratio >= desc_threshold:
                reason.append(f"描述相似{d_ratio:.2f}")
            best = {
                "ku_id": ku.get("ku_id", ""),
                "title": ku.get("title", ""),
                "title_ratio": round(t_ratio, 3),
                "desc_ratio": round(d_ratio, 3),
                "reason": "；".join(reason),
                "_score": score,
            }
    if best:
        best.pop("_score", None)
    return best
