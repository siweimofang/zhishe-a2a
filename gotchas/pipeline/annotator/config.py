"""
配置层：路径常量 + .env 读取（零第三方依赖）。

路径解析基于本文件自身位置，部署到 gotchas/pipeline/annotator/ 后自动指向正确目录：
    annotator/config.py
      parents[0] = annotator
      parents[1] = pipeline
      parents[2] = gotchas
      parents[3] = zhishe-a2a（.env 所在）
"""
import os
from pathlib import Path

# ── 目录锚点 ──
ANNOTATOR_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = ANNOTATOR_DIR.parent
GOTCHAS_DIR = PIPELINE_DIR.parent
ZHISHE_ROOT = GOTCHAS_DIR.parent

# ── 数据文件路径 ──
SCHEMA_PATH = GOTCHAS_DIR / "schema" / "ku_schema_v1.json"
TAXONOMY_PATH = GOTCHAS_DIR / "schema" / "taxonomy_v1.json"
ALL_KU_PATH = GOTCHAS_DIR / "data" / "v1.0" / "all_ku.json"
PENDING_PATH = GOTCHAS_DIR / "data" / "drafts" / "pending_review.json"
STATS_PATH = GOTCHAS_DIR / "metadata" / "stats.json"
BY_STAGE_DIR = GOTCHAS_DIR / "data" / "v1.0" / "by_stage"
BY_SEVERITY_DIR = GOTCHAS_DIR / "data" / "v1.0" / "by_severity"
RELATIONS_PATH = GOTCHAS_DIR / "relations" / "ku_relations_v1.json"
INPUT_DIR = PIPELINE_DIR / "input"
BACKUP_DIR = PIPELINE_DIR / "backup"
CHECKPOINT_PATH = PIPELINE_DIR / ".checkpoint.json"

# ── .env 路径 ──
ENV_PATH = ZHISHE_ROOT / ".env"


def _parse_env_file(path: Path) -> dict:
    """手动解析 .env（KEY=VALUE 行），兼容 UTF-8 BOM、空行、# 注释。零依赖。"""
    result = {}
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8-sig")  # utf-8-sig 自动剥离 BOM
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


_env_cache = None


def get_env() -> dict:
    """读取并缓存 .env 键值。"""
    global _env_cache
    if _env_cache is None:
        _env_cache = _parse_env_file(ENV_PATH)
    return _env_cache


def get_deepseek_config() -> dict:
    """返回 DeepSeek 调用所需配置。key 缺失时抛 RuntimeError（不静默）。"""
    env = get_env()
    api_key = env.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            f"DEEPSEEK_API_KEY 未在 {ENV_PATH} 中配置，流水线无法调用模型。"
        )
    return {
        "api_key": api_key,
        "base_url": env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "model": env.get("DEEPSEEK_MODEL", "deepseek-chat"),
    }


def mask_key(key: str) -> str:
    """脱敏展示 key（仅用于日志/报告）。"""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-4:]}"


# ── 业务常量（与 spec/plan 第六节决策一致）──
DEDUP_TITLE_THRESHOLD = 0.8   # 标题相似度阈值
DEDUP_DESC_THRESHOLD = 0.7    # 描述相似度阈值
MAX_FIELD_LEN = 500           # description/how_to_avoid 上限（schema）
MIN_FIELD_LEN = 50            # description/how_to_avoid 下限（schema）
MIN_MATERIAL_LEN = 20         # 素材片段最短字数
EXTRACT_MAX_RETRY = 2         # 抽取失败重试次数
QUALITY_ON_APPROVE = "REFERENCE"  # 审核通过升级到的质量等级
