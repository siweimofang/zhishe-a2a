# Gotchas库 AI辅助标注流水线 — 需求规格说明书（spec.md）

> 版本：v1.0（待审查）
> 日期：2026-08-01
> 作者：知设AI助手
> 依据：知设Gotchas库项目书_v1.0、ku_schema_v1.1.json、taxonomy_v1.json、gap_analysis_v1.0.md
> 开发流程：遵循 constitution.md 的 Spec-Driven 五步法，本文件为 Step 1 产物

---

## 〇、为什么要做（背景与结论先行）

**结论**：DEEPSEEK_API_KEY 已查实并非卡点（key 实测有效、.env 配置正常）。真正缺的是"AI辅助标注流水线"这台工具本身——gotchas 目录目前只有数据、没有任何批量生产 KU 的代码。

**现状数字（2026-08-01 stats.json）**：
- 总 KU 数：60 条；关联关系：116 条
- 质量分布：RELIABLE 42 + CERTIFIED 1 + REFERENCE 17
- Phase 1 目标已校准为 **200-300 条 RELIABLE+**，当前 RELIABLE+ 仅 43 条，**缺口约 157-257 条**
- 空白维度：STAGE_06（软装进场）0 条、TRADE_FLOOR（地板）0 条

**本工具的定位**：把小马哥 20 年装修经验的原始口述/笔记，批量、自动地转成符合 schema 的标准 KU，先落待审区（DRAFT），人工审核后升级入库。目标是将"手工逐条磨"升级为"流水线批量产 + 人工把关"，一次性解决数量瓶颈。

---

## 一、功能点清单

| 编号 | 功能 | 优先级 | 说明 |
|------|------|--------|------|
| F1 | 经验素材进料 | P0 | 读取一个文本/Markdown 文件，里面是小马哥口述或笔记形式的装修经验（可一段含多个坑点） |
| F2 | AI 抽取候选 KU | P0 | 调 DeepSeek，按 schema 字段结构化抽取，一条素材可产出多条候选 KU（JSON 输出） |
| F3 | Schema 与枚举校验 | P0 | 用 ku_schema_v1.json 做结构校验，用 taxonomy_v1.json 做枚举值校验，不合格打回 |
| F4 | 自动编号 | P0 | 扫描现有 all_ku.json 取最大 GZ-SY-XXXXX，递增分配，保证不重号 |
| F5 | 自动打标 | P0 | 自动写 metadata：created_by=ai、quality_level=DRAFT、verified=false、created_at=当天 |
| F6 | 去重检查 | P1 | 候选 KU 与现有库做标题/描述相似度比对，疑似重复的标记出来交人工裁决 |
| F7 | 落待审区 | P0 | 校验通过的候选写入 data/drafts/pending_review.json |
| F8 | 标注报告 | P1 | 每批输出报告：投入素材数、产出候选数、校验通过数、打回数及原因、疑似重复数 |
| F9 | 人工审核 CLI | P0 | 逐条展示待审 KU，支持 通过/丢弃/现场改 三种操作 |
| F10 | 入库与升级 | P0 | 审核通过的 KU 升级 quality_level→REFERENCE、verified→true，合并进 all_ku.json |
| F11 | 索引重建 | P0 | 入库后自动重建 by_stage / by_severity 分片文件，刷新 stats.json |
| F12 | 关联建议 | P2 | 入库时基于阶段/工种相同，给出候选 related_ku_ids 供人工确认（非强制） |

---

## 二、用户场景（User Story）

**US-1（核心路径）**：作为知设创始人，我把最近整理的"瓦工/瓷砖"经验笔记存成一个 txt，运行流水线，它自动产出十几条标准 KU 草稿放到待审区，我逐条审一遍，通过的直接入库，几分钟完成过去半天的活。

**US-2（质量把关）**：作为审核者，我在审核 CLI 里看到一条候选 KU 的 description 只有 40 字（不满足 schema 最少 50 字），它根本没进待审区——流水线在校验阶段就拦下并报告给我，避免脏数据入库。

**US-3（防重复）**：作为审核者，流水线发现我新投喂的"水电按米虚报"和库里 GZ-SY-00003 高度相似，在报告里标黄提醒，我据此决定是合并还是丢弃，不让库里出现两条几乎一样的 KU。

**US-4（断点续传）**：作为操作者，一批素材跑到一半 DeepSeek 接口超时，流水线记下跑到哪了，我重跑时从断点继续，不重复花钱、不重复产出。

---

## 三、验收标准（Acceptance Criteria）

1. 给定一段包含 3 个独立坑点的经验文本，流水线能产出 ≥1 条结构合法的候选 KU，且 ku_id 唯一、枚举值全部落在 taxonomy 范围内。
2. 任何不满足 ku_schema_v1.json required 字段（ku_id/title/stage/role/severity/description/how_to_avoid）的候选，100% 被拦截在待审区之外，并在报告里给出具体原因。
3. 运行结束后 pending_review.json 是合法 JSON 数组；入库后 all_ku.json、by_stage/*、by_severity/*、stats.json 四者数据一致（总数对得上）。
4. 人工审核 CLI 对一条 KU 的"通过"操作，会使其 quality_level 从 DRAFT 变为 REFERENCE、verified 变为 true，且从 pending_review.json 移除。
5. 全程不硬编码任何 API key，DeepSeek key 一律从 zhishe-a2a/.env 读取。
6. 单批 50 条素材跑完，标注报告完整输出各项计数，无静默失败。
7. 单元测试覆盖：schema 校验、枚举校验、自动编号、去重判定四个核心函数，覆盖率 ≥70%（constitution Phase 1 要求）。

---

## 四、边界条件与异常处理

| 场景 | 处理策略 |
|------|----------|
| DeepSeek 返回非 JSON / 字段缺失 | 重试最多 2 次；仍失败则该条素材记为"抽取失败"，不中断整批 |
| 接口超时 / 限流（HTTP 429/5xx） | 指数退避重试；记录断点，支持续跑 |
| 素材文本为空或过短（<20字） | 跳过并在报告标注"素材过短" |
| 枚举值越界（如 AI 编了个 STAGE_99） | 校验拦截，打回，不入库 |
| ku_id 冲突（并发或脏数据） | 以 all_ku.json 实时最大值为准，分配前再扫一次 |
| pending_review.json 损坏（非合法 JSON） | 读取报错时备份原文件为 .bak，重建空数组，提示人工 |
| 同一素材重复投喂 | 去重检查命中，标记疑似重复交人工裁决 |
| description/how_to_avoid 超长（>500字） | 校验拦截或自动截断到 500 字并标注（二选一，plan 阶段定） |

---

## 五、明确不做（本期范围外）

- 不做外部资料（中消协/国标）的自动抓取与清洗——本期进料口只接"经验投喂"，外部源留待二期。
- 不做关联关系的自动写库（116 条 CO_OCCURS 的细化）——本期只给建议，人工确认，避免污染关系图。
- 不做 Web 界面——审核用命令行即可，符合一人创业轻资产原则。
- 不碰 zhishe-a2a 后端服务代码——本工具是独立的离线脚本，只读写 gotchas 数据文件。

---

## 六、待确认项（clarify 清单，供 Step 2 用）

1. 超长字段（description/how_to_avoid >500字）：自动截断 还是 打回重写？
2. 去重相似度阈值定多少（建议标题≥0.8 或描述≥0.7 视为疑似重复）？
3. 审核通过时默认升到 REFERENCE 还是 RELIABLE？（schema 升级路径规定 DRAFT→REFERENCE 需人工审核通过，REFERENCE→RELIABLE 需第二来源验证。建议本期审核通过=REFERENCE，符合规范。）
4. 进料文件格式：纯 txt / Markdown / 还是约定一个简单模板（如每条经验用 --- 分隔）？
