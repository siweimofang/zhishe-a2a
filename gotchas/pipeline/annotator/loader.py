"""
进料层：读取素材文件，按 --- 分隔符切成经验片段。

约定（spec 已确认）：纯文本/Markdown 文件，多条经验之间用单独一行 --- 分隔。
若整个文件没有 ---，则视为单条素材整体处理。
"""
from pathlib import Path
from typing import List

from . import config


def load_material(path: Path, min_len: int = config.MIN_MATERIAL_LEN) -> dict:
    """
    读取素材文件并切分。

    返回:
        {
            "raw": 原始全文,
            "segments": [非空且达到最短字数的片段],
            "skipped_short": [被判定过短的片段],
        }
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"素材文件不存在: {path}")

    raw = path.read_text(encoding="utf-8-sig")
    # 按单独成行的 --- 切分（兼容 --- 前后有空行）
    parts = _split_by_separator(raw)

    segments: List[str] = []
    skipped_short: List[str] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        # 字数按去空白后的字符数估算
        if len(text) < min_len:
            skipped_short.append(text)
        else:
            segments.append(text)

    return {"raw": raw, "segments": segments, "skipped_short": skipped_short}


def _split_by_separator(text: str) -> List[str]:
    """按单独成行的 --- 切分。无分隔符则返回整体。"""
    lines = text.splitlines()
    chunks: List[str] = []
    current: List[str] = []
    sep_seen = False
    for line in lines:
        if line.strip() == "---":
            sep_seen = True
            chunks.append("\n".join(current))
            current = []
        else:
            current.append(line)
    chunks.append("\n".join(current))
    if not sep_seen:
        # 没有分隔符，整体作为一条
        return [text]
    return chunks
