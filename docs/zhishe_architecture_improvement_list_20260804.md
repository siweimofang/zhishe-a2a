# 知设架构改进清单（基于两篇 L3 归档）

> 生成日期：2026-08-04 ｜ 依据归档：
> [deepseek_v4flash_harness_analysis_20260804.md](./deepseek_v4flash_harness_analysis_20260804.md)（L3）
> [graph_engineering_agent_analysis_20260804.md](./graph_engineering_agent_analysis_20260804.md)（L3）
> 核心共识：模型实际能力 = 潜在能力 × Harness 释放效率；Agent 可靠性上限 = 控制流设计，不取决于模型智商。

---

## 一、两篇核心结论合并

| 文章 | 核心洞察 | 对知设的直接落点 |
|---|---|---|
| DeepSeek V4-Flash 后训练 | 性能提升 = 模型权重 + Harness 系统；Agent 训练瓶颈是"可大量产生失败轨迹的环境" | Gotchas 库 = 装修行业"失败环境"；Skill+Harness 路线获战略级验证 |
| Graph Engineering | 系统可靠性取决于控制流设计；State/Nodes/Edges/Gates；围绕失败设计五种结果；验证必须独立于创造 | 现有 P0-P6 流水线已是 Graph 雏形，缺显式失败路径、独立验证分支、预算管理 |

**两篇的共同指向**：能力不在模型里，在系统里。一个在"系统层"（Harness 释放能力），一个在"控制流层"（Graph 保证可靠）。知设的 Skill+Gotchas 正是前者，本清单解决后者。

---

## 二、改进项 A：独立验证体系（最高优先，直接对应"验证必须独立于创造"）

### A.0 现状问题（反模式确认）

现有 598 条 KU 的验证字段为 `verify_method: "multi_source" / "ai_cross_reference"`——即**生成与验证是同一主体**（同一模型、同一会话上下文）。多源交叉引用 ≠ 独立验证：验证者的推理链里带着"我为什么这样写"的记忆，自我核验存在确认偏差，正对应文章"同一个 Agent 既创造又批准自己的内容，会成为一个糟糕的怀疑者"；且"一个薄弱假设会成为下一步的'证据'"——错误会在逐条入库中自我复制。

### A.1 流程治理（层 0）

- 新入库条目默认 `quality_level: "PENDING"`，`verified: False`；只有跑完验证流水线才升级 `RELIABLE`
- 禁止"生成者在同一会话给自己打 RELIABLE"（约束入库脚本与人工操作规范）
- 每条目记录 `metadata.verified_by: {"model": "...", "method": "...", "rule_version": "...", "date": "..."}`——验证主体可追溯

### A.2 确定性规则 Gate（层 1，零模型、纯代码）

新增 `gotchas/data/v1.0/verification_rules.json`：从已核实强条提取可机读"真理表"：

| 规则类别 | 示例（已入库强条） |
|---|---|
| 数值限值 | 甲醛≤0.07mg/m³、苯≤0.06、TVOC≤0.45、氨≤0.15、氡≤150Bq/m³（GB 50325-2020 6.0.4） |
| 几何尺寸 | 净高≥2.40m（局部≥2.10m 且≤1/3 面积）、厨卫净高≥2.20m、护栏 1.05/1.10m、杆件净距≤0.11m、楼梯井>0.11m 须防攀滑（GB 50096 5.5.2/6.3.2/6.3.5） |
| 工艺参数 | 空鼓率≤10%/间≤5%、水压 0.6-0.8MPa 保压 30min 降压≤0.05MPa、防水卷起 300mm/淋浴区 1.8m、蓄水 24h、吊点距≤1200mm、起拱 1/200-1/300 |
| 引用一致性 | standard_number 与 evidence.source_ref 一致；related_ku_ids 存在且非悬空（test_p0 Part2 已有基础，升级为常驻校验） |
| 效力状态 | 废止条文清单（GB 50210-2018 五条强条 2023-03-01 废止）；引用废止条文必须含承接说明（GB 55032-2022） |

规则引擎校验 KU 文本中出现的数值与真理表一致，输出结构化：
`{"decision": "pass", "failed_rules": [], "evidence": [{"rule_id": "GB50325-6.0.4-fa", "matched": 0.07}]}`

### A.3 独立验证 Agent Gate（层 2，不同模型 + 不同上下文）

- **不同模型**：生成用 DeepSeek V4（主底座），验证用第二家模型（GLM/Kimi/通义任一），API 成本按离线批处理可接受
- **上下文隔离**：验证 Agent 只输入三样东西——候选 KU 全文、标准原文锚点（原文章节/条款摘录）、verification_rules.json；**不输入**生成过程的任何对话、推理链、中间结论
- **结构化输出**（照 Graph 工程模板，返回证据不返回感觉）：
  `{"decision": "pass/retry/fail", "failed_rule": "clause_mismatch", "unsupported_claims": [3, 7], "evidence": "原文第X条：..."}`

### A.4 人工 Escalate Gate（层 3）

以下必须人工复核队列（进 `PENDING` 待审区，不直接入库）：强条（standard_authority=national 且含"强制性条文"）、SEV_CRITICAL、验证判 fail、层 1 与层 2 结论冲突的条目；其余按比例抽检。

### A.5 周期复验（层 4，时间隔离）

- 对存量 `verified_by` 为"生成者自证"的条目（约 60+ 条 standard）排期用层 1+层 2 重验
- 复验间隔：强条类季度、一般条目半年；`expires_at` 字段启用

### A.6 与现有资产的衔接

- `test_p0.py` Part2（schema/悬空引用校验）→ 层 1 的常驻部分，纳入验证流水线脚本而非一次性测试
- 新增 `gotchas/pipeline/validate_ku.py`：批处理入口（598 条全量跑层 1 应为秒级；层 2 按批调第二模型）
- 新增 `/gotchas/audit` 端点（或本地脚本）：返回质量分布（PENDING/RELIABLE/已验证主体统计）

---

## 三、改进项 B：检索失败处理显式化（Retry / Reroute / Escalate / Stop）

现状：P0-P6 管线无显式失败分支（代码中无 retry 逻辑），检索失败后无后续动作。

| 文章概念 | 知设设计 | 触发条件 |
|---|---|---|
| Retry | 换扩展词重查（query_rewriter 已存在，触发重写后二次检索） | 双召回总命中数 < 阈值 或 Top-1 置信度 < 阈值 |
| Reroute | 切换领域专家提示词（standard_ask_v1 / gotchas_ask_v1 / mixed_ask_v1） | knowledge_type 分类置信度低、跨领域冲突（如"防水"同时命中施工与材料） |
| Escalate | 挂起待人工（设计师人工审核节点） | 高风险建议（报价、结构改动、强条适用判断） |
| Stop | 返回最佳部分结果 + 明确失败原因 | Token/时间预算耗尽；重试次数超限 |

落地顺序：先加 Stop Rule（防死循环，成本最低）→ 再 Retry → 最后 Reroute/Escalate。

---

## 四、改进项 C：三预算管理（谈单分析 Agent 场景）

| 预算 | 文章原则 | 知设实现 |
|---|---|---|
| Token 预算 | 传结构化证据，不传聊天记录 | 谈单分析各节点（客户画像/谈单记录/设计师 Schema）传 Evidence 摘要而非原始对话；每节点 Token 上限 |
| 时间预算 | 并行分支汇合点等最慢分支 | 分析任务设整体截止时间，超时返回部分结论 |
| 风险预算 | "读取文档和发送付款不应共享同一权限策略" | 高风险动作（报价生成、承诺性建议）与普通检索分离权限与额度 |

---

## 五、改进项 D：P0-P6 流水线 Graph 显式映射（现状盘点）

| 流水线组件 | Graph 角色 | 缺口 |
|---|---|---|
| 领域映射（25 条规则，0.67ms） | Nodes（确定性） | 无 |
| query_rewriter（LLM 扩展） | Nodes | 无显式失败处理（见改进项 B） |
| BM25 + TF-IDF 双召回 | 并行 Edges | 无 |
| RRF 融合 | Synthesis 节点 | 无 |
| FeatureReranker 精排 | Gate（部分） | 置信度阈值未显式化 |
| /ask 三套提示词 | 条件 Edges（按 knowledge_type 路由） | 分类置信度低时无 Reroute |
| **缺失** | Challenge 节点（独立验证答案） | 改进项 A 解决 |
| **缺失** | Stop/Retry 边 | 改进项 B 解决 |

---

## 六、阶段规划

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| P0（近期） | 层 1 确定性规则引擎 + verification_rules.json + verified_by 字段改造 + 新条目默认 PENDING | 598 条全量层 1 校验跑通；强条数值零误标；无"自证 RELIABLE"新条目 |
| P1（短期） | 层 2 独立模型验证（第二家模型批处理）+ 人工复核队列 + 存量 60+ 条重验 | 全部 standard 条目带 verified_by（非生成者）；抽查一致性 ≥ 95% |
| P2（中期） | 改进项 B：Stop → Retry → Reroute/Escalate 显式化；/gotchas/audit 端点 | 检索空结果/低置信场景有明确后续动作；audit 返回质量分布 |
| P3（远期） | 改进项 C 三预算、D 完整 Graph 建模 | 谈单 Agent 预算超限有部分结果返回；架构图与实现一致 |

---

## 七、一句话结论

Prompt 让模型更聪明，Graph 让系统更可靠，Harness 让能力被释放——知设已有后两者的雏形（Gotchas 库 + P0-P6 流水线），本清单把缺失的"独立验证、失败路径、预算管理"显式化。**第一步动作：新入库条目停止自证 RELIABLE，跑层 1 规则引擎。**
