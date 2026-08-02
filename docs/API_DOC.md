# 知设 Gotchas API 文档

> 基础地址：`https://tunnel.zhishe.top`
> 版本：V1.1 | 更新：2026-08-02
> 状态：生产运行中

## 架构概览

```
外部调用者
    │
    ├── /gotchas/search  → 摘要（防爬，目录级信息）
    ├── /gotchas/ask     → 自然语言回答（完整体验，不暴露结构化数据）
    ├── /gotchas/        → KU列表（摘要）
    ├── /gotchas/{id}    → 单条摘要
    ├── /gotchas/stats   → 统计信息
    └── /gotchas/gaps    → 覆盖空白分析

内部（小程序后端/自有服务）
    │
    └── 直接读 all_ku.json → 完整532条KU结构化数据
```

**安全原则：** 外部只给"答案"和"目录"，不给"数据"。完整KU内容（description/typical_scenario/trigger_keywords/causal_chain/evidence/metadata）不通过任何公开端点暴露。

---

## 端点详情

### GET /gotchas/ask（推荐 - 自然语言问答）

装修避坑问答。输入自然语言问题，返回AI生成的口语化回答。

**参数：**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| q | string | 是 | - | 装修问题（自然语言，≥2字） |
| context_kus | int | 否 | 3 | 内部参考知识条数（1-5） |

**响应示例：**

```json
{
  "question": "闭水试验到底要做多久",
  "answer": "闭水试验最少24小时，这是底线...前2个小时是重点观察期，你要跑到楼下邻居家盯着管道根部、墙角看。如果这两三个小时内楼下就渗水了，说明防水层有明确毛病，不用傻等满24小时，直接叫工人返工修补...",
  "sources": [
    {"ku_id": "GZ-SY-00298", "title": "闭水试验未做或走过场致防水缺陷遗漏"},
    {"ku_id": "GZ-SY-00011", "title": "防水必须刷2-3遍+24小时闭水试验，仅刷一遍等于没做"}
  ],
  "engine": "gotchas_ask_v1"
}
```

**特点：**
- 回答为自然语言，150-300字，老师傅口吻
- 不返回结构化字段（无severity/stage/trade/description等）
- 来源只给ku_id + title，不给内容
- 降级：DeepSeek不可用时返回how_to_avoid摘要（engine=fallback_no_llm）

**调用示例：**
```
GET https://tunnel.zhishe.top/gotchas/ask?q=水管走顶好还是走地好
```

---

### GET /gotchas/search（结构化检索 - 摘要级）

混合检索引擎（BM25 + TF-IDF + RRF + 精排 + P6领域映射）。返回匹配的KU摘要。

**参数：**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| q | string | 是 | - | 搜索关键词 |
| stage | string | 否 | - | 阶段过滤：STAGE_01~08 |
| trade | string | 否 | - | 工种过滤：TRADE_PLUMBING等 |
| min_severity | string | 否 | - | 最低严重度：SEV_CRITICAL/HIGH/MEDIUM/LOW |
| limit | int | 否 | 10 | 返回条数（1-50） |
| use_rewriter | bool | 否 | true | 启用P5+P6查询改写 |

**响应示例：**

```json
{
  "query": "防水刷几遍",
  "engine": "hybrid_p6",
  "total": 10,
  "results": [
    {
      "score": 0.4206,
      "rank_bm25": 1,
      "rank_tfidf": 2,
      "ku": {
        "ku_id": "GZ-SY-00141",
        "title": "防水面积按实际单独计算易漏",
        "severity": "SEV_HIGH",
        "stage": "STAGE_04",
        "trade": ["TRADE_WATERPROOF"],
        "how_to_avoid_brief": "1. 合同中明确防水按实际涂刷面积计算，而非按地面面积估算。2. 要..."
      }
    }
  ]
}
```

**注意：** `how_to_avoid_brief` 截断为50字。完整内容不通过此端点提供。

---

### GET /gotchas/（KU列表 - 摘要级）

列出KU，支持多维筛选。返回摘要格式。

**参数：** stage, severity, scope, trade, role, problem_type, quality_level, min_severity, limit(≤200), offset

**响应：** `{total, offset, limit, count, kus: [摘要对象]}`

---

### GET /gotchas/{ku_id}（单条摘要）

返回指定KU的公开摘要。完整内容需授权（未开放）。

---

### GET /gotchas/stats（统计信息）

返回库的统计概况（阶段/严重度/工种/质量等级分布）。无敏感内容。

---

### GET /gotchas/gaps（覆盖空白分析）

返回库的覆盖空白和补充建议。无敏感内容。

---

## 访问限制

| 项目 | 当前状态 | 计划 |
|------|---------|------|
| 认证 | 无（公开） | Phase1加API Key |
| 频率限制 | 无 | 未登录10次/天，登录50次/天 |
| Cloudflare防护 | Bot Fight Mode（拦截非浏览器UA） | 保持 |
| 内容暴露 | 摘要+自然语言回答 | 完整内容仅内部/授权 |

**注意：** Cloudflare Bot Fight Mode会拦截Python/curl默认User-Agent（返回error 1010）。调用时需携带浏览器UA头：
```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
```

---

## 引擎说明

| engine值 | 含义 |
|----------|------|
| gotchas_ask_v1 | /ask端点，DeepSeek生成自然语言回答 |
| hybrid_p6 | P0-P6全链路混合检索（BM25+TF-IDF+RRF+精排+领域映射） |
| substring_fallback | 检索器不可用时的子串匹配降级 |
| fallback_no_llm | /ask端点DeepSeek不可用，返回摘要 |
| fallback_llm_error | /ask端点DeepSeek调用失败，返回摘要 |

---

## 变更日志

- 2026-08-02: 新增/gotchas/ask自然语言回答层；所有端点加_public_summary防爬
- 2026-08-01: /gotchas/search升级为hybrid_p6引擎
- 2026-07-31: Gotchas库V1.0上线（532条KU）
