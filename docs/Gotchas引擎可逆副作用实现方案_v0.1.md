# Gotchas 引擎可逆副作用实现方案 v0.1

**日期**：2026-08-17 | **依据**：情报-15（DSH 论文：可逆副作用/余效应/汇流性定理，L3 9.5分）+ Gotchas 引擎现状调研（2026-08-17 实测）
**目标**：把"规则可热更新、变更可回滚、动态系统可当静态系统推理"落到 Gotchas 引擎（598 条 KU，/gotchas/ask 链路）
**定位**：P1 架构升级，分四阶段实施，每阶段可独立上线

---

## 一、问题定义：现状的四个痛点

| 痛点 | 现状 | 后果 |
|---|---|---|
| 无热更新 | 模块 import 时一次性 `_load_data()`，改 all_ku.json 必须重启进程 | 规则修正/新增的反馈回路 = 重启级，运维成本高 |
| 无回滚 | 无变更记录、无逆操作 | 一条坏规则入库后只能手动改文件+重启，不能"撤销" |
| 无钩子机制 | ask 链路直通（检索→拼上下文→LLM→返回），无插件点 | guard（rate_limit/detect_probe/watermark）无法接入 gotchas，检索前后无法挂横切逻辑 |
| 全局单例 | 模块级 `_ku_cache`/`_ku_index` 直接读写 | 无法替换/多实例/测试注入 |

**理论映射**（情报-15）：上述痛点全部是"动态组合"问题——规则增删改=时间组合（可逆副作用解决）、钩子与依赖=空间组合（余效应解决）、热更新一致性=汇流性问题（幂等重建解决）。

## 二、架构设计：三个新模块

```
gotchas/runtime/
├── effects.py      # EffectRegistry：副作用注册表（LIFO 逆函数累加器）
├── rule_manager.py # RuleManager：规则生命周期管理（增/改/删/批量加载）
└── hooks.py        # HookManager：检索管线钩子（余效应拦截）
```

### 2.1 effects.py —— 逆函数累加器（核心）

```python
# gotchas/runtime/effects.py
"""可逆副作用注册表：逆函数在施加那一刻写出，LIFO 累积，复合逆自动派生。"""

@dataclass
class Effect:
    id: str                 # 全局唯一，如 "rule.add.GZ-SY-0001"
    name: str               # 人类可读，如 "新增规则:水电开槽深度"
    apply: Callable[[], None]    # 施加动作（副作用本体）
    undo: Callable[[], None]     # 逆函数——写 apply 时必须同时交出
    guard: Callable[[], bool] = field(default=lambda: True)  # 余效应守卫
    state: str = "PENDING"  # PENDING → APPLIED → ROLLED_BACK

class EffectRegistry:
    """LIFO 逆函数累加器。支持单条回滚、批量回滚、全量回滚。"""

    def __init__(self):
        self._stack: list[Effect] = []
        self._by_id: dict[str, Effect] = {}
        self._history: list[dict] = []   # 变更事件日志（审计/可观测）

    def apply(self, e: Effect) -> Effect:
        """施加副作用。守卫不通过则跳过（余效应：依赖未就绪不激活）。"""
        if not e.guard():
            e.state = "SKIPPED"
            return e
        e.apply()
        e.state = "APPLIED"
        self._stack.append(e)
        self._by_id[e.id] = e
        self._history.append({"id": e.id, "name": e.name, "op": "apply", "at": time_now()})
        return e

    def rollback(self, effect_id: str) -> bool:
        """按 id 回滚。默认只允许回滚栈顶（保证 LIFO 顺序）；带 force 可跳过守卫。"""
        ...

    def rollback_batch(self, batch_id: str) -> list[str]:
        """回滚同一批次的所有 Effect——复合逆由组合自动得出，逆序执行各自 undo。"""
        ...

    def rollback_all(self) -> list[str]:
        """全量回滚（进程退出前/加载失败时兜底）。"""
        while self._stack:
            e = self._stack.pop()
            e.undo(); e.state = "ROLLED_BACK"
        ...

    # UNLOADING 中间态（情报-15 最难半个定理）：
    # undo 执行时可能还需要即将消失的依赖——两条规则：
    #   R1 停止对外提供，但保留依赖视图（先摘钩子、再拆数据）
    #   R2 守卫条件：还有组件依赖就不许执行回滚（记录 pending，依赖解除后补执行）
    def _unloading(self, e: Effect):
        """摘除对外能力（R1），数据回滚（R2）两步走，带守卫。"""
        ...
```

**关键约定（工程铁律）**：任何副作用写 `apply` 时必须同时写 `undo`——代码审查规则 + 类型层面（Effect 构造缺 undo 即 TypeError）。

### 2.2 rule_manager.py —— 规则生命周期

```
生命周期：REGISTERED → ACTIVE → UNLOADING → REMOVED
```

| 操作 | apply（施加时） | undo（逆函数，施加时写出） |
|---|---|---|
| add_rule(ku) | `_ku_cache[ku_id]=ku`；索引标 dirty | 删缓存项；索引恢复原状态（dirty 重算） |
| update_rule(ku_id, new_ku) | 旧版本快照存入 effect；新版本覆盖 | 恢复旧版本快照（内存+索引一致） |
| remove_rule(ku_id) | 快照旧数据；删缓存项 | 按快照原样恢复 |
| load_batch(kus, batch_id) | 逐条 add（共享 batch_id） | 逆序逐条 undo——复合逆自动派生 |
| reload_all() | 备份当前全部缓存+索引状态；重载 all_ku.json；索引 dirty | 恢复备份（等价于没发生过重载） |

```python
# gotchas/runtime/rule_manager.py
class RuleManager:
    def __init__(self, registry: EffectRegistry, cache: dict, index):
        self._reg = registry
        self._cache = cache          # 现有 _ku_cache
        self._index = index          # 现有 _ku_index

    def add_rule(self, ku: dict) -> Effect:
        ku_id = ku["ku_id"]
        snapshot = ku  # 新增无旧值，undo 只需删除
        def apply():
            self._cache[ku_id] = ku
            mark_dirty(self._index)          # 见 §3 汇流性
        def undo():
            self._cache.pop(ku_id, None)
            mark_dirty(self._index)
        return Effect(f"rule.add.{ku_id}", f"新增规则:{ku['title']}", apply, undo)

    def update_rule(self, ku_id: str, new_ku: dict) -> Effect:
        old = self._cache.get(ku_id)
        if old is None: raise KeyError(ku_id)
        def apply():
            self._cache[ku_id] = new_ku
            mark_dirty(self._index)
        def undo():
            self._cache[ku_id] = old           # 快照恢复——"销毁从产生派生"
            mark_dirty(self._index)
        return Effect(f"rule.update.{ku_id}", f"更新规则:{new_ku['title']}", apply, undo)

    def remove_rule(self, ku_id: str) -> Effect:
        old = self._cache.get(ku_id)
        if old is None: raise KeyError(ku_id)
        def apply():
            self._cache.pop(ku_id, None)
            mark_dirty(self._index)
        def undo():
            self._cache[ku_id] = old           # 按原数据恢复
            mark_dirty(self._index)
        return Effect(f"rule.remove.{ku_id}", f"删除规则:{old['title']}", apply, undo)

    def load_batch(self, kus: list[dict], batch_id: str) -> list[Effect]:
        """批量加载=复合副作用；回滚逆序执行各自 undo（汇流性保证结果一致）。"""
        return [self.add_rule(ku) for ku in kus]   # 同一 batch_id 由调用方登记
```

### 2.3 hooks.py —— 余效应拦截（检索管线钩子）

```python
# gotchas/runtime/hooks.py
class HookPoint(str, Enum):
    PRE_SEARCH   = "pre_search"    # 查询改写后、检索前（权限/范围过滤、query 审计）
    POST_SEARCH  = "post_search"   # 检索后、拼上下文前（结果过滤/脱敏/severity 门槛）
    PRE_LLM      = "pre_llm"       # 拼上下文后、调 LLM 前（缓存命中/价格档位选择）
    POST_LLM     = "post_llm"      # LLM 返回后、响应前（水印/免责/合规校验）

@dataclass
class Hook:
    point: HookPoint
    fn: Callable[[HookCtx], HookCtx]   # 纯函数式管道：入参 ctx 出参 ctx
    deps: list[str] = field(default_factory=list)   # 余效应：依赖规格声明
    enabled: bool = True

class HookManager:
    """钩子注册返回 Effect（undo=注销）——钩子本身就是可逆副作用。"""

    def __init__(self, registry: EffectRegistry):
        self._reg = registry
        self._hooks: dict[HookPoint, list[Hook]] = defaultdict(list)

    def register(self, hook: Hook) -> Effect:
        def apply(): self._hooks[hook.point].append(hook)
        def undo(): self._hooks[hook.point].remove(hook)
        return self._reg.apply(Effect(f"hook.{hook.point}.{id(hook)}", f"挂载钩子:{hook.point}", apply, undo))

    def run(self, point: HookPoint, ctx: HookCtx) -> HookCtx:
        """依赖未就绪的钩子跳过（不激活）而非报错——余效应语义。"""
        for hook in list(self._hooks[point]):
            if not hook.enabled: continue
            if any(dep not in ctx.services for dep in hook.deps): continue   # 不激活
            ctx = hook.fn(ctx)
        return ctx
```

## 三、汇流性设计：热更新后"当静态系统推理"

**定理落点**：无论经历怎样的增删改序列，最终检索状态 = 一次性加载最终规则集的状态。

**实现（与现状天然兼容）**：
1. 所有规则变更只做两件事：改 `_ku_cache`（数据）+ 标记 `dirty`（索引失效）
2. 索引重建是**幂等**的：`build_index()` 从 `_ku_cache` 全量重建（现状已是如此，598 条秒级）——重建结果只取决于静止时的规则集，与历史无关
3. 惰性重建：检索前检查 dirty，dirty 则重建一次再查——首次热更新后检索有一次"重建成本"，之后 O(1) 摊销

```
规则变更序列（任意）───► dirty 标记 ──► 下次检索前幂等重建 ──► 状态与历史无关 ✅
```

**推论**：回滚 undo 只需改缓存+dirty，不需要手动"修复索引"——索引永远从最终数据推导，天然满足汇流性。

## 四、API 端点（admin 面）

```
POST   /gotchas/admin/rules               # 新增规则（body=KU json）
PUT    /gotchas/admin/rules/{ku_id}       # 更新规则
DELETE /gotchas/admin/rules/{ku_id}       # 删除规则（undo 保留快照）
POST   /gotchas/admin/rules/batch         # 批量加载（body=KU[]，带 batch_id）
POST   /gotchas/admin/reload              # 重载 all_ku.json（整批 Effect）
POST   /gotchas/admin/rollback            # 回滚最近一批（body: {batch_id} 或空=栈顶）
GET    /gotchas/admin/effects             # 副作用注册表状态（审计/可观测）
```

安全：admin 端点独立鉴权（`A2A_ADMIN_KEY`，与 ask 的只读 key 分离）；所有变更写 `_history` 事件日志（谁/何时/改了什么/能否回滚）——可观测性从第一天建（情报-05）。

## 五、与现有代码的改造点（精确清单）

| 文件 | 改造 |
|---|---|
| `gotchas_api.py` | ①`_load_data()` 改为可重载（拆出 `reload_data()`，保留 import 时初载）；②ask 链路插 4 个钩子点（`hooks.run(...)`，默认无钩子=行为不变）；③新增 admin 路由块；④`_ku_cache`/`_ku_index` 移交 RuleManager 管理（模块级全局保留引用，避免大改） |
| `app/api/guard.py` | 现有 `rate_limit`/`detect_probe`/`apply_watermark` 封装为 Hook 接入：rate_limit→PRE_SEARCH（依赖 auth）、detect_probe→POST_SEARCH、apply_watermark→POST_LLM——**顺带补上"guard 未接入 gotchas"的现状缺口** |
| `gotchas/retriever/searcher.py` | `build_index()` 增加幂等契约注释+dirty 检查入口（不改检索逻辑） |
| `app/main.py` | 启动时初始化 `EffectRegistry`（可选：退出钩子 rollback_all） |

**零破坏原则**：默认行为与现状完全一致（无钩子、无变更=无 dirty、admin 未用=无感知）。全部改造向后兼容。

## 六、分阶段实施路线

| 阶段 | 内容 | 交付物 | 前置 |
|---|---|---|---|
| P1-1 | effects.py + rule_manager.py + admin 端点（增/改/删/回滚） | 热更新+回滚能力上线 | 无（纯增量模块） |
| P1-2 | 钩子点接入 ask 链路 + guard 三件套封装为 Hook | 防护能力补全+管线可扩展 | P1-1 |
| P2 | 变更事件日志可视化（/admin/effects）+ 回滚演练脚本 | 可观测性闭环 | P1-2 |
| P3 | 创造模式（远期）：临时规则/临时钩子（进程内存，重启消失，情报-15 终局形态） | 自演化 Agent 基础 | 情报-04 Harness-R1 路线图对齐 |

## 七、验收标准

1. **可逆**：新增一条规则→检索命中→rollback→检索回到原状（索引一致）
2. **复合逆**：批量加载 10 条→回滚批次→10 条全部消失且无残留（无孤儿缓存项）
3. **汇流性**：任意序列（增→删→改→增）后的检索结果 = 直接加载最终规则集的结果（diff 为空）
4. **UNLOADING**：删除"被引用规则"（related_ku_ids 指向）时触发守卫——拒绝或延迟到引用解除
5. **零破坏**：无 admin 调用时，/gotchas/ask 行为与改造前逐字节一致（回归测试）

---

**设计原理一句话**：让每个规则变更在施加那一刻交出自己的逆函数（LIFO 累积），让索引从数据幂等推导（汇流性），让横切逻辑以钩子挂载且依赖未就绪不激活（余效应）——Gotchas 从"重启才能改的静态库"变成"可推理、可撤销、可热更新的运行时系统"。

---

## 八、实现补充说明(2026-08-17 已落地)

代码位置:`gotchas/runtime/{effects,rule_manager,hooks}.py` + `app/api/gotchas_api.py` 集成。

1. **protected 系统级保护**(验收5 补强):钩子注册本身是副作用,混在业务副作用栈中,
   运维执行 `/admin/rollback`(整体回滚)会误杀防护钩子 → Effect 增加 `protected` 字段:
   `rollback_all` 默认跳过 protected(压回栈,状态保持 APPLIED,单条 rollback 仍可精确注销),
   仅 `force=True` 连根清除。guard 三件套钩子均 protected。
2. **汇流性落地路径**:RuleManager 只改缓存+`_mark_index_dirty()`;检索前 `_ensure_index()`
   调 `searcher.set_data(_ku_cache)`(内存直通,新增方法)+ `build_index()` 幂等重建 ——
   全程不落盘,热更新立即生效;`persist()` 显式调用才写盘(带 .bak 备份)。
3. **重载引用稳定性**:`_reload_data()` 用 `clear()/extend()` 就地更新,保持列表对象引用,
   RuleManager 持有的缓存引用在 reload 后依然有效。
4. **UNLOADING 语义**:R1(`begin_unload`)拒收新副作用;R2(`finish_unload`)带守卫回滚
   (guard()=False 的保留待人工处理,protected 一律保留);`cancel_unload()` 可撤回 R1。
5. **admin 端点**:`/gotchas/admin/{rules,rules/{ku_id},rules/batch,reload,rollback,effects,status,unload}`,
   `A2A_ADMIN_KEY` 独立鉴权,未配置 → 503(不本地放行);挂在 /gotchas 下同时受业务 key 约束(双 key)。
   管理密钥走独立请求头 `X-Admin-Key` —— Authorization 已被业务密钥占用,
   共用同一头两依赖互相覆盖(实测 401,已修复)。
6. **测试**:`gotchas/tests/test_runtime_effects.py` 41 项断言,5 条验收标准全过;
   guard 三件套(限流/探测/水印)已作为钩子接入 ask/search 链路,补齐存量缺口。

## 九、P2 事件日志可视化(2026-08-17 已落地)

1. **运维面板** `static/gotchas_admin.html`:单文件(无外部依赖),访问 `/static/gotchas_admin.html`。
   鉴权区(双密钥仅存页面内存,刷新重输)+ 状态卡(6 项,5 秒轮询,页面不可见时暂停)+
   事件流时间线(类型彩色标签:施加绿/回滚橙/失败红/跳过灰,支持类型/关键词/批次筛选)+
   操作区(回滚最新一条/按 ID/按批次/全量 + 卸载 R1/R2/cancel + 重载),破坏性操作先弹确认。
2. **回滚演练脚本** `scripts/gotchas_rollback_drill.py`:一键闭环(热新增→检索命中→批次回滚→
   检索消失→状态复核),6 步 PASS 输出报告,退出码 0/1;密钥从 .env 读取不回显;
   演练规则 GZ-DRILL-<ts> 与业务库隔离,失败路径 finally 兜底清理。实测 6/6 通过。
3. **rollback 端点新增 mode=top**:回滚栈顶"业务"副作用(跳过 protected 系统钩子 ——
   初始实现直接取栈顶,实测误回滚 guard_watermark 钩子,已修;仅剩系统钩子时返回
   ok=false + 提示,不误杀)。单条 rollback(effect_id) 仍不受 protected 限制(明确指定可精确回滚)。
4. **unload 端点新增 stage=cancel**:撤回 R1(registry.cancel_unload() 本就存在,API 面补齐)。
5. **P2 计划文档**:`docs/下一阶段开发计划_P2事件可视化_P3创造模式_v1.0.md`
   (含 P3 调研结论:情报-04 Harness-R1 路线图仓库内不存在,技术推演 + 解锁条件)。
