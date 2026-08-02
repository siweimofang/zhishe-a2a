"""
Gotchas库 V1.1 API Router
知设结构化知识库的REST API接口

端点:
  GET  /gotchas/              — 列出KU（支持多维筛选）
  GET  /gotchas/stats         — 统计信息
  GET  /gotchas/gaps          — 空白分析
  GET  /gotchas/search        — 文本搜索
  GET  /gotchas/relations     — 全部关联关系
  GET  /gotchas/{ku_id}       — 单条KU详情
  GET  /gotchas/{ku_id}/related — 关联KU
  POST /gotchas/log           — 记录KU使用日志
"""

import json
import os
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# ── 数据路径 ──
GOTCHAS_DIR = Path(__file__).resolve().parent.parent.parent / "gotchas"
ALL_KU_PATH = GOTCHAS_DIR / "data" / "v1.0" / "all_ku.json"
RELATIONS_PATH = GOTCHAS_DIR / "relations" / "ku_relations_v1.json"
STATS_PATH = GOTCHAS_DIR / "metadata" / "stats.json"
USAGE_LOG_PATH = GOTCHAS_DIR / "logs" / "usage_log.json"

# ── Router ──
router = APIRouter(prefix="/gotchas", tags=["gotchas"])


# ── 数据加载（启动时加载到内存） ──
_ku_cache: list = []
_ku_index: dict = {}
_relations_cache: list = []


def _load_data():
    """加载KU和关联关系到内存"""
    global _ku_cache, _ku_index, _relations_cache

    if ALL_KU_PATH.exists():
        with open(ALL_KU_PATH, "r", encoding="utf-8") as f:
            _ku_cache = json.load(f)
        _ku_index = {ku["ku_id"]: ku for ku in _ku_cache}

    if RELATIONS_PATH.exists():
        with open(RELATIONS_PATH, "r", encoding="utf-8") as f:
            _relations_cache = json.load(f)


# 模块加载时初始化
_load_data()

# ── P0-P6 检索系统初始化 ──
_hybrid_searcher = None

def _init_retriever():
    """初始化GotchasHybrid检索器（懒加载，失败不影响其他API）"""
    global _hybrid_searcher
    try:
        import sys
        sys.path.insert(0, str(GOTCHAS_DIR.parent))
        from gotchas.retriever import GotchasHybrid, QueryRewriter
        _hybrid_searcher = GotchasHybrid(str(GOTCHAS_DIR))
        _hybrid_searcher.build_index()
        rewriter = QueryRewriter()
        _hybrid_searcher.enable_rewriter(rewriter)
        print(f"[Gotchas] Retriever initialized: {len(_hybrid_searcher.all_ku)} docs, rewriter={'on' if rewriter.enabled else 'domain-only'}")
    except Exception as e:
        print(f"[Gotchas] Retriever init failed (fallback to substring): {e}")
        _hybrid_searcher = None

_init_retriever()


# ── 辅助函数 ──
def _filter_kus(
    kus: list,
    stage: Optional[str] = None,
    severity: Optional[str] = None,
    scope: Optional[str] = None,
    trade: Optional[str] = None,
    role: Optional[str] = None,
    problem_type: Optional[str] = None,
    quality_level: Optional[str] = None,
    min_severity: Optional[str] = None,
) -> list:
    """多维筛选KU"""
    result = kus
    severity_order = {"SEV_LOW": 0, "SEV_MEDIUM": 1, "SEV_HIGH": 2, "SEV_CRITICAL": 3}

    if stage:
        result = [ku for ku in result if ku.get("stage") == stage]
    if severity:
        result = [ku for ku in result if ku.get("severity") == severity]
    if scope:
        result = [ku for ku in result if ku.get("scope") == scope]
    if trade:
        result = [ku for ku in result if trade in ku.get("trade", [])]
    if role:
        result = [ku for ku in result if role in ku.get("role", [])]
    if problem_type:
        result = [ku for ku in result if problem_type in ku.get("problem_type", [])]
    if quality_level:
        result = [ku for ku in result if ku.get("metadata", {}).get("quality_level") == quality_level]
    if min_severity:
        min_val = severity_order.get(min_severity, 0)
        result = [ku for ku in result if severity_order.get(ku.get("severity", "SEV_LOW"), 0) >= min_val]

    return result


# ── 请求/响应模型 ──
class UsageLogEntry(BaseModel):
    ku_id: str
    source_channel: str = "api_direct"
    user_query: Optional[str] = None
    user_helpful: Optional[bool] = None
    response_snippet: Optional[str] = None


class UsageLogResponse(BaseModel):
    log_id: str
    status: str


# ══════════════════════════════════════════
# 端点实现
# ══════════════════════════════════════════

@router.get("/")
def list_kus(
    stage: Optional[str] = Query(None, description="装修阶段: STAGE_01~08"),
    severity: Optional[str] = Query(None, description="严重度: SEV_CRITICAL/HIGH/MEDIUM/LOW"),
    scope: Optional[str] = Query(None, description="适用范围: universal/regional:north/regional:shenyang"),
    trade: Optional[str] = Query(None, description="工种: TRADE_PLUMBING/TILE/..."),
    role: Optional[str] = Query(None, description="角色: ROLE_OWNER/DESIGNER/CONTRACTOR/INDUSTRY"),
    problem_type: Optional[str] = Query(None, description="问题类型: TYPE_FRAUD/QUALITY/..."),
    quality_level: Optional[str] = Query(None, description="质量等级: CERTIFIED/RELIABLE/REFERENCE/DRAFT"),
    min_severity: Optional[str] = Query(None, description="最低严重度: 只返回此级别及以上"),
    limit: int = Query(50, ge=1, le=200, description="返回数量上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """列出KU，支持多维筛选。"""
    filtered = _filter_kus(
        _ku_cache, stage, severity, scope, trade, role, problem_type, quality_level, min_severity
    )
    total = len(filtered)
    page = filtered[offset: offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "count": len(page),
        "kus": page,
    }


@router.get("/stats")
def get_stats():
    """获取Gotchas库统计信息。"""
    if STATS_PATH.exists():
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    # 如果文件不存在，实时计算
    return _compute_stats()


@router.get("/gaps")
def get_gaps():
    """分析Gotchas库的覆盖空白。"""
    all_stages = [f"STAGE_0{i}" for i in range(1, 9)]
    stage_names = {
        "STAGE_01": "前期准备", "STAGE_02": "设计阶段", "STAGE_03": "报价签约",
        "STAGE_04": "施工阶段", "STAGE_05": "主材安装", "STAGE_06": "软装进场",
        "STAGE_07": "验收交付", "STAGE_08": "售后维保",
    }
    all_trades = [
        "TRADE_DESIGN", "TRADE_DEMOLISH", "TRADE_PLUMBING", "TRADE_WATERPROOF",
        "TRADE_TILE", "TRADE_CARPENTRY", "TRADE_PAINT", "TRADE_CABINET",
        "TRADE_DOOR", "TRADE_FLOOR", "TRADE_BATHROOM", "TRADE_ELECTRICAL",
    ]
    trade_names = {
        "TRADE_DESIGN": "设计", "TRADE_DEMOLISH": "拆改", "TRADE_PLUMBING": "水电",
        "TRADE_WATERPROOF": "防水", "TRADE_TILE": "瓦工/瓷砖", "TRADE_CARPENTRY": "木工",
        "TRADE_PAINT": "油工/涂料", "TRADE_CABINET": "橱柜定制", "TRADE_DOOR": "门窗",
        "TRADE_FLOOR": "地板", "TRADE_BATHROOM": "卫浴", "TRADE_ELECTRICAL": "电气/智能家居",
    }

    stage_count = {}
    trade_count = {}
    for ku in _ku_cache:
        s = ku.get("stage", "")
        stage_count[s] = stage_count.get(s, 0) + 1
        for t in ku.get("trade", []):
            trade_count[t] = trade_count.get(t, 0) + 1

    empty_stages = [
        {"code": s, "name": stage_names[s], "count": 0}
        for s in all_stages if s not in stage_count
    ]
    weak_stages = [
        {"code": s, "name": stage_names[s], "count": stage_count[s]}
        for s in all_stages if s in stage_count and stage_count[s] < 10
    ]
    empty_trades = [
        {"code": t, "name": trade_names[t], "count": 0}
        for t in all_trades if t not in trade_count
    ]
    weak_trades = [
        {"code": t, "name": trade_names[t], "count": trade_count[t]}
        for t in all_trades if t in trade_count and trade_count[t] < 5
    ]

    return {
        "total_kus": len(_ku_cache),
        "stages_covered": f"{len(stage_count)}/8",
        "trades_covered": f"{len(trade_count)}/12",
        "empty_stages": empty_stages,
        "weak_stages": weak_stages,
        "empty_trades": empty_trades,
        "weak_trades": weak_trades,
        "recommendations": _generate_recommendations(stage_count, trade_count),
    }


@router.get("/search")
def search_kus(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    stage: Optional[str] = None,
    trade: Optional[str] = None,
    min_severity: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    use_rewriter: bool = Query(True, description="启用P5+P6查询改写"),
):
    """
    Gotchas智能检索（P0-P6全链路）
    
    检索链路: 领域映射 -> LLM扩展 -> BM25+TF-IDF双路 -> RRF融合 -> 精排
    降级策略: 检索器不可用时回退到子串匹配
    """
    # 优先使用Hybrid检索器
    if _hybrid_searcher is not None:
        try:
            results = _hybrid_searcher.search(
                q, top_n=limit,
                stage=stage, trade=trade,
                min_severity=min_severity,
                use_rewriter=use_rewriter
            )
            return {
                "query": q,
                "engine": "hybrid_p6",
                "total": len(results),
                "results": [
                    {
                        "score": r["score"],
                        "rank_bm25": r["rank_bm25"],
                        "rank_tfidf": r["rank_tfidf"],
                        "ku": {
                            "ku_id": r["ku_id"],
                            "title": r["title"],
                            "severity": r["severity"],
                            "stage": r["stage"],
                            "trade": r["trade"],
                            "typical_scenario": r["scenario"],
                            "how_to_avoid": r["avoid"],
                            "trigger_keywords": r["keywords"],
                        }
                    }
                    for r in results
                ],
            }
        except Exception as e:
            pass  # 降级到子串匹配

    # 降级: 子串匹配
    q_lower = q.lower()
    results = []
    for ku in _ku_cache:
        if stage and ku.get("stage") != stage:
            continue
        text = " ".join([
            ku.get("title", ""),
            ku.get("description", ""),
            ku.get("how_to_avoid", ""),
            ku.get("typical_scenario", ""),
        ]).lower()
        if q_lower in text:
            score = text.count(q_lower)
            results.append({"score": score, "ku": ku})

    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "query": q,
        "engine": "substring_fallback",
        "total": len(results),
        "results": results[:limit],
    }


@router.get("/relations")
def list_relations(
    ku_id: Optional[str] = Query(None, description="筛选某个KU的关联"),
    relation_type: Optional[str] = Query(None, description="关系类型: CAUSES/CO_OCCURS/SOLVED_BY/PREVENTED_BY/ESCALATES_TO"),
):
    """列出所有关联关系，可按KU或类型筛选。"""
    rels = _relations_cache
    if ku_id:
        rels = [r for r in rels if r.get("source_ku_id") == ku_id or r.get("target_ku_id") == ku_id]
    if relation_type:
        rels = [r for r in rels if r.get("relation_type") == relation_type]
    return {
        "total": len(rels),
        "relations": rels,
    }


@router.get("/{ku_id}")
def get_ku(ku_id: str):
    """获取单条KU详情。"""
    ku = _ku_index.get(ku_id)
    if not ku:
        raise HTTPException(status_code=404, detail=f"KU not found: {ku_id}")
    return ku


@router.get("/{ku_id}/related")
def get_related_kus(ku_id: str):
    """获取某条KU的关联KU列表。"""
    ku = _ku_index.get(ku_id)
    if not ku:
        raise HTTPException(status_code=404, detail=f"KU not found: {ku_id}")

    direct_rels = [
        r for r in _relations_cache
        if r.get("source_ku_id") == ku_id or r.get("target_ku_id") == ku_id
    ]

    related = []
    for rel in direct_rels:
        other_id = rel["target_ku_id"] if rel["source_ku_id"] == ku_id else rel["source_ku_id"]
        other_ku = _ku_index.get(other_id)
        if other_ku:
            related.append({
                "relation_type": rel.get("relation_type"),
                "description": rel.get("description", ""),
                "ku": other_ku,
            })

    # 从KU自身的related_ku_ids中找（可能有未在relations文件中记录的）
    seen_ids = {r["ku"]["ku_id"] for r in related}
    for rid in ku.get("related_ku_ids", []):
        if rid not in seen_ids:
            other = _ku_index.get(rid)
            if other:
                related.append({
                    "relation_type": "CO_OCCURS",
                    "description": "KU自身标注的关联",
                    "ku": other,
                })

    return {
        "ku_id": ku_id,
        "total": len(related),
        "related": related,
    }


@router.post("/log", response_model=UsageLogResponse)
def log_usage(entry: UsageLogEntry):
    """记录KU使用日志（反馈闭环）。"""
    if entry.ku_id not in _ku_index:
        raise HTTPException(status_code=404, detail=f"KU not found: {entry.ku_id}")

    now = datetime.now()
    log_id = f"LOG-{now.strftime('%Y%m%d')}-{_get_log_count() + 1:05d}"

    log_entry = {
        "log_id": log_id,
        "ku_id": entry.ku_id,
        "timestamp": now.isoformat(),
        "source_channel": entry.source_channel,
        "user_query": entry.user_query,
        "user_helpful": entry.user_helpful,
        "response_snippet": entry.response_snippet,
    }

    logs = []
    if USAGE_LOG_PATH.exists():
        try:
            with open(USAGE_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            logs = []

    logs.append(log_entry)

    with open(USAGE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

    return UsageLogResponse(log_id=log_id, status="recorded")


# ── 内部辅助 ──
def _get_log_count() -> int:
    if USAGE_LOG_PATH.exists():
        try:
            with open(USAGE_LOG_PATH, "r", encoding="utf-8") as f:
                return len(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return 0


def _compute_stats() -> dict:
    stage_map = {}
    sev_map = {}
    scope_map = {}
    role_map = {}
    trade_map = {}
    ql_map = {}

    for ku in _ku_cache:
        s = ku.get("stage", "")
        stage_map[s] = stage_map.get(s, 0) + 1
        sv = ku.get("severity", "")
        sev_map[sv] = sev_map.get(sv, 0) + 1
        sc = ku.get("scope", "unknown")
        scope_map[sc] = scope_map.get(sc, 0) + 1
        for r in ku.get("role", []):
            role_map[r] = role_map.get(r, 0) + 1
        for t in ku.get("trade", []):
            trade_map[t] = trade_map.get(t, 0) + 1
        ql = ku.get("metadata", {}).get("quality_level", "UNKNOWN")
        ql_map[ql] = ql_map.get(ql, 0) + 1

    return {
        "total_kus": len(_ku_cache),
        "total_relations": len(_relations_cache),
        "by_stage": dict(sorted(stage_map.items())),
        "by_severity": dict(sorted(sev_map.items())),
        "by_scope": dict(sorted(scope_map.items())),
        "by_role": dict(sorted(role_map.items())),
        "by_trade": dict(sorted(trade_map.items())),
        "quality_levels": ql_map,
    }


def _generate_recommendations(stage_count: dict, trade_count: dict) -> list:
    recs = []
    stage_names = {
        "STAGE_01": "前期准备", "STAGE_02": "设计阶段", "STAGE_03": "报价签约",
        "STAGE_04": "施工阶段", "STAGE_05": "主材安装", "STAGE_06": "软装进场",
        "STAGE_07": "验收交付", "STAGE_08": "售后维保",
    }
    for s, name in stage_names.items():
        c = stage_count.get(s, 0)
        if c == 0:
            recs.append(f"P0: {name}({s})完全空白，需立即补充")
        elif c < 10:
            recs.append(f"P1: {name}({s})仅{c}条，建议扩充至20+")

    if "TRADE_FLOOR" not in trade_count:
        recs.append("P0: 地板(TRADE_FLOOR)工种完全空白")

    return recs
