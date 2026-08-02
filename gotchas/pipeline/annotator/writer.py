"""
落盘层：把校验通过的候选写入待审区 pending_review.json。

待审区格式（数组）：
[
  {
    "ku": {完整 KU},
    "duplicate_hint": null 或 {ku_id,title,title_ratio,desc_ratio,reason},
    "added_at": "YYYY-MM-DDTHH:MM:SS",
    "source": "素材文件名#片段序号"
  },
  ...
]

损坏保护：读取时若非合法 JSON，自动备份为 .bak 并重建空数组。
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from . import config


def load_pending(pending_path: Path = config.PENDING_PATH) -> List[dict]:
    """读取待审区；损坏时备份并返回空列表。"""
    if not pending_path.exists():
        return []
    try:
        with open(pending_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("待审区顶层不是数组")
        return data
    except (json.JSONDecodeError, ValueError):
        backup = pending_path.with_suffix(".json.bak")
        shutil.copy2(pending_path, backup)
        print(f"[警告] 待审区损坏，已备份到 {backup}，重建为空数组。")
        return []


def save_pending(items: List[dict], pending_path: Path = config.PENDING_PATH) -> None:
    """原子写入待审区（先写临时再替换）。"""
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pending_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    tmp.replace(pending_path)


def append_pending(
    new_entries: List[dict], pending_path: Path = config.PENDING_PATH
) -> int:
    """追加新待审条目，返回追加后总数。"""
    items = load_pending(pending_path)
    items.extend(new_entries)
    save_pending(items, pending_path)
    return len(items)


def make_entry(ku: dict, duplicate_hint: dict = None, source: str = "") -> dict:
    """构造一条待审条目。"""
    return {
        "ku": ku,
        "duplicate_hint": duplicate_hint,
        "added_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
    }
