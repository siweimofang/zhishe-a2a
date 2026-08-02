# Gotchas库版本变更记录

## V1.0 (2026-07-31) - 种子数据初始化

### 新增
- 创建KU Schema V1.0（ku_schema_v1.json）
- 创建分类标签枚举定义（taxonomy_v1.json）
- 从现有知识资产中筛选并转换20条种子KU
- 建立8阶段×4严重度的分类文件结构
- 创建KU关联关系图（37条关联）

### 数据来源
- knowledge.json（60条Q&A，筛选出10条真正的Gotcha）
- skills/*/gotchas.md（9个Skill共35条Gotcha，筛选出8条）
- 其余knowledge.json条目为参考数据（价格基准/城市系数/品牌推荐），不属于Gotcha范畴

### 筛选标准
- 入库铁律：真实性 + 普遍性 + 可行动性（三项必须同时满足）
- 排除：纯参考信息（价格基准、城市系数、品牌推荐、建材市场列表）
- 排除：非Gotcha的通用装修知识（基础知识、百科内容）

### 覆盖情况
- 阶段覆盖：7/8（缺：stage_06_软装进场）
- 严重度覆盖：SEV_CRITICAL=4, SEV_HIGH=9, SEV_MEDIUM=6, SEV_LOW=1
- 质量等级：RELIABLE=14, REFERENCE=6

### 待补充
- STAGE_06（软装进场）：0条，需要采集家具/窗帘/灯具/家电相关Gotcha
- STAGE_01（前期准备）：仅1条，需要补充收房验房、预算规划相关Gotcha
- 各阶段需大量扩充至项目书目标数量

## V1.1 — 2026-08-01

### Schema升级
- 新增 `metadata.expires_at` 字段（日期/null），支持知识保鲜机制
- 新增 `metadata.last_reviewed_at` 字段（日期），记录上次人工审查时间
- 新增顶层 `scope` 字段（枚举：universal/regional:shenyang/regional:north/regional:south/regional:other），支持通用层+地域层分离

### 60条KU标注
- 全部60条KU已完成scope标注：universal 52条，regional:north 7条，regional:shenyang 1条
- 全部60条KU已添加expires_at（默认null=永久有效）和last_reviewed_at（2026-08-01）

### 反馈日志设计
- 新增 `logs/` 目录
- 新增 `logs/usage_log_schema_v1.json`（使用日志Schema）
- 新增 `logs/usage_log.json`（空日志文件，待Agent集成后填充）
- 新增 `logs/README.md`（使用说明）

### 目标校准
- Phase 1目标从10000条校准为200-300条高质量(RELIABLE/CERTIFIED)KU
- 当前RELIABLE+数量：43/60

### 设计决策记录
1. **通用/地域分离**：V1.0用scope字段标注，V2.0考虑ku_id前缀分离（GZ-xxx通用/GZ-SY-xxx地域）
2. **知识保鲜**：expires_at默认null，建议每6个月审查一次，通过last_reviewed_at追踪
3. **反馈闭环**：V1.0用JSON日志文件，V2.0迁移到SQLite并实现分析仪表盘
4. **关联关系**：当前116条CO_OCCURS手动维护，V1.1开始设计自动关联pipeline
