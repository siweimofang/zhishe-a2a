# Gotchas库 AI辅助标注流水线 — 技术方案（plan.md）

> 版本：v1.0（待审查）
> 日期：2026-08-01
> 依据：spec.md v1.0、constitution.md、ku_schema_v1.1.json、taxonomy_v1.json
> 开发流程：Spec-Driven Step 3 产物（Step 4 任务拆解见第七节）

---

## 一、技术选型与理由

| 项 | 选型 | 理由 |
|----|------|------|
| 语言 | Python 3.12+ | constitution 强制；与 zhishe-a2a 后端同栈，复用 .env 读取逻辑 |
| 大模型 | DeepSeek（deepseek-chat @ api.deepseek.com） | key 已验证有效；后端 llm.py 已用同一家；结构化抽取够用且便宜 |
| 调用方式 | 标准库 urllib + 原生 HTTPS | 不引第三方 SDK，轻资产；与后端 llm.py 风格一致 |
| 配置读取 | python-dotenv 读 zhishe-a2a/.env | 复用现有 key，绝不硬编码（constitution 安全红线） |
| Schema 校验 | jsonschema 库 | ku_schema_v1.json 本身就是 draft-07，直接拿来校验，零额外维护 |
| 相似度去重 | difflib.SequenceMatcher（标准库） | 不引 numpy/sklearn，60-300 条规模标准库足够，秒级 |
| 数据格式 | JSON（沿用现有 gotchas 文件） | 与 all_ku.json/stats.json 完全一致，不破坏后端 gotchas_api 读取 |
| 测试 | pytest | constitution 指定 |

**不选的方案及原因**：
- 不用 LangChain 等重型框架——constitution 禁止重型框架，且本工具逻辑线性，框架纯属负担。
- 不建数据库——gotchas 现有就是 JSON 文件 + 后端内存加载，引入 DB 会割裂架构。
- 不用异步并发调模型——批量小（几十条/批），串行 + 重试更稳更省，符合"稳"字方针。

---

## 二、架构模式

采用**分层 + 流水线（pipeline）**结构，单向数据流，每层职责单一：

```
[素材文件 txt/md]
      │  ① 进料层 loader
      ▼
[原始经验片段列表]
      │  ② 抽取层 extractor（调 DeepSeek，出候选 KU dict）
      ▼
[候选 KU（未校验）]
      │  ③ 校验层 validator（jsonschema + 枚举 + 编号 + 打标）
      ▼
[合法候选 KU（DRAFT）] ──④ 去重层 dedup（标记疑似重复）
      │  ⑤ 落盘层 writer
      ▼
[pending_review.json 待审区]
      │  ⑥ 审核 CLI reviewer（人工 通过/丢弃/改）
      ▼
[all_ku.json + by_stage/* + by_severity/* + stats.json]（⑦ 索引重建 rebuilder）
```

**目录结构**（新增于 gotchas/pipeline/，不动现有数据文件）：

```
gotchas/pipeline/
├── spec.md / plan.md          ← 本方案
├── annotator/
│   ├── __init__.py
│   ├── config.py              ← 读 .env、路径常量
│   ├── loader.py              ← ① 进料
│   ├── extractor.py           ← ② 调 DeepSeek 抽取
│   ├── validator.py           ← ③ 校验+编号+打标
│   ├── dedup.py               ← ④ 去重
│   ├── writer.py              ← ⑤ 落待审区
│   ├── rebuilder.py           ← ⑦ 重建分片+stats
│   └── prompts.py             ← 抽取用的提示词模板
├── run_annotate.py            ← 主入口：跑一批
├── run_review.py              ← 主入口：审核 CLI
├── tests/
│   ├── test_validator.py
│   ├── test_dedup.py
│   └── test_numbering.py
└── input/                     ← 小马哥投喂的素材放这里
    └── README.md
```

---

## 三、数据设计

不新增数据库，只约定文件读写契约（全部沿用现有格式）：

**读取**：
- `zhishe-a2a/.env` → DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL、DEEPSEEK_MODEL
- `gotchas/schema/ku_schema_v1.json` → 校验依据
- `gotchas/schema/taxonomy_v1.json` → 枚举白名单
- `gotchas/data/v1.0/all_ku.json` → 取最大编号 + 去重比对
- `gotchas/data/drafts/pending_review.json` → 待审区（当前为 `[]`）

**写入**：
- `pending_review.json` ← 校验通过的 DRAFT 候选（数组追加）
- 审核通过后：`all_ku.json`（追加）、`by_stage/stage_0X_*.json`（重建）、`by_severity/sev_*.json`（重建）、`stats.json`（重算）

**候选 KU 数据契约**：与 ku_schema_v1.json 完全一致，AI 抽取时强制输出的字段：
`title, stage, role[], severity, problem_type[], trade[], material[], description, typical_scenario, how_to_avoid, evidence{source_type,confidence}, causal_chain{...}, scope`
编号（ku_id）与 metadata 由 validator 自动补，不让 AI 编（防止 AI 乱填编号/质量等级）。

---

## 四、接口规范

本工具是离线脚本，无 HTTP 接口。对外表现为两个命令行入口：

**4.1 标注入口**
```
python run_annotate.py --input input/瓦工瓷砖.txt [--dry-run] [--resume]
```
- `--input`：素材文件路径（必填）
- `--dry-run`：只抽取校验、打印报告，不写 pending_review.json
- `--resume`：从上次断点续跑
- 退出码：0=成功，1=有失败条目（报告里列明），2=配置/环境错误

**4.2 审核入口**
```
python run_review.py
```
- 逐条打印待审 KU（标题/描述/避坑/阶段/工种/严重度）
- 交互命令：`y`=通过入库 / `n`=丢弃 / `e`=现场编辑后再决定 / `s`=跳过留待下次 / `q`=退出
- 每次 `y` 即时触发 rebuilder，保证四文件一致

**4.3 与 DeepSeek 的接口**（内部）
- POST `{DEEPSEEK_BASE_URL}/chat/completions`，model 取 .env 的 DEEPSEEK_MODEL
- 提示词要求模型只返回 JSON 数组，temperature 调低（0.2）保证稳定
- 响应解析失败 → 重试 2 次 → 仍失败记"抽取失败"

---

## 五、第三方依赖清单

| 依赖 | 版本 | 用途 | 是否新增 |
|------|------|------|----------|
| python-dotenv | ≥1.0 | 读 .env | 后端已用，复用 |
| jsonschema | ≥4.0 | schema 校验 | 新增（轻量纯 Python） |
| pytest | ≥7.0 | 测试 | 后端已用，复用 |

标准库承担：urllib（HTTP）、difflib（去重）、json、pathlib、argparse、re。
**刻意不引**：requests、langchain、openai SDK、numpy——保持轻资产（constitution）。

---

## 六、关键设计决策（已替你想清楚，可推翻）

1. **编号不让 AI 填**：AI 只产出内容字段，ku_id 和 metadata 由代码统一补。理由：AI 编编号极易重号/跳号，代码扫最大值递增最稳。
2. **审核通过 = REFERENCE**（非 RELIABLE）：严格遵循 taxonomy 的升级路径（DRAFT→REFERENCE 靠人工审核，REFERENCE→RELIABLE 需第二来源验证）。这样库的质量分级不注水。
3. **超长字段打回而非截断**：description/how_to_avoid 超 500 字直接打回让 AI 重抽一次，仍超再人工。理由：截断会破坏语义完整性，宁可重抽。
4. **去重阈值**：标题相似度 ≥0.8 或描述 ≥0.7 判为疑似重复，只标记不自动丢，交人工裁决。
5. **串行 + 指数退避**：不并发，每条间隔短延时，429/超时退避重试。批量小，稳优先。

---

## 七、任务拆解（Step 4，每项 ≤2 小时）

| 序号 | 任务 | 输入 | 输出/验收 | 预估 |
|------|------|------|-----------|------|
| T1 | 搭骨架 + config.py（读 .env、路径常量） | .env | 能打印出 key 长度/模型名，不泄露全文 | 0.5h |
| T2 | validator.py（jsonschema+枚举校验+自动编号+打标） | schema/taxonomy | 单测：非法枚举/缺字段被拦、编号递增正确 | 1.5h |
| T3 | prompts.py + extractor.py（调 DeepSeek 出候选） | 素材片段 | 给一段文本能返回合法 JSON 候选数组 | 1.5h |
| T4 | loader.py（切分素材为片段） | txt/md | 按分隔符切出片段列表，过短跳过 | 0.5h |
| T5 | dedup.py（相似度比对） | 候选+all_ku | 单测：相同标题判重、不同判通过 | 1h |
| T6 | writer.py（落 pending_review.json，含损坏备份） | 合法候选 | 待审区追加成功，损坏时自动 .bak | 1h |
| T7 | run_annotate.py 主流程串联 + 报告 + 断点 | 以上模块 | 跑通一批，报告完整，--dry-run 可用 | 1.5h |
| T8 | rebuilder.py（重建分片+stats） | all_ku | 入库后四文件总数一致 | 1h |
| T9 | run_review.py 审核 CLI | pending_review | 通过/丢弃/编辑/跳过都生效 | 1.5h |
| T10 | 端到端联调 + 补单测到覆盖率≥70% | 全模块 | pytest 全绿，真实跑一批瓦工素材入库 | 1.5h |

**合计约 11.5 小时**，可分 2-3 个工作日完成。依赖链：T1→T2→T3→T4 可并行起步，T7 依赖 T2-T6，T9-T10 收尾。

---

## 八、风险与回滚

- **风险1：AI 抽取质量不稳**。对策：temperature 调低 + 强校验 + 人工审核三道关，脏数据进不了正式库（最多污染待审区，可一键清空）。
- **风险2：误改 all_ku.json**。对策：rebuilder 每次写入前先备份 all_ku.json 到 pipeline/backup/，出问题可回滚。
- **风险3：DeepSeek 费用**。对策：--dry-run 先验证不写库；批量小、串行，单批成本可忽略（deepseek-chat 极便宜）。
- **回滚**：本工具完全独立，不碰后端服务；最坏情况删除 gotchas/pipeline/ 目录即恢复原状，数据文件有备份。

---

## 九、三大壁垒 / 六字方针自查（constitution 要求）

- 数据隐私：素材与 KU 全部本地存储，不上公有云；key 从 .env 读，不硬编码、不进日志。✅
- 行业对齐：产出直接沉淀进 Gotchas 库（KU 格式），强化核心壁垒。✅
- 小快灵稳准狠：独立轻脚本（小）、约 2 天（快）、可 --dry-run 可回滚（灵）、三道质量关（稳）、直击数量瓶颈（准）、巩固 Gotchas 壁垒（狠）。✅
