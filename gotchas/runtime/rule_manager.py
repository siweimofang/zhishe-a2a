"""
RuleManager 规则热更新管理器 (v0.1)
====================================
汇流性实现:所有规则变更只改内存缓存(cache/index)并标记 dirty,
不直接写磁盘。下次检索前由 gotchas_api._ensure_index() 幂等重建索引
(searcher.set_data 内存直通),最终状态只取决于当前缓存 —— 与操作历史无关。

每个操作生成一个 Effect 登记到 EffectRegistry(可逆副作用账本):
- add_rule     undo = 从缓存删除
- update_rule  undo = 恢复旧快照
- remove_rule  undo = 恢复快照
- load_batch   undo = 按逆序恢复全部快照(复合逆自动派生)

约定:cache 与 index 必须始终同步 —— 本模块内部唯一维护者,
任何增删改都走 _replace / _delete,禁止外部直接改。
"""

import copy
import time
from typing import Callable, Dict, List, Optional

from .effects import Effect, EffectRegistry

DEFAULT_BATCH_ID = "batch"  # load_batch 未显式给 batch_id 时的默认批次
MAX_TEMP_RULES = 50         # 临时规则总量上限(防 Agent 失控创建)


class RuleManager:
    """规则热更新管理器(持有缓存引用,变更登记进注册表)。"""

    def __init__(
        self,
        cache: list,
        index: dict,
        registry: Optional[EffectRegistry] = None,
        mark_dirty: Optional[Callable[[], None]] = None,
        max_temp_rules: int = MAX_TEMP_RULES,
    ) -> None:
        self._cache = cache                 # gotchas_api._ku_cache 的引用(同一对象)
        self._index = index                 # gotchas_api._ku_index 的引用
        self._registry = registry or EffectRegistry()
        self._mark_dirty = mark_dirty or (lambda: None)
        self._max_temp_rules = max_temp_rules
        self._temp_counter = 0              # 临时规则序号计数器(TMP-<ts>-<seq>)
        self._temp_rule_ids = set()         # 当前栈内未回滚的临时规则 ku_id 集合

    # ══════════ 只读 ══════════

    @property
    def registry(self) -> EffectRegistry:
        return self._registry

    def count(self) -> int:
        return len(self._cache)

    def exists(self, ku_id: str) -> bool:
        return ku_id in self._index

    def get(self, ku_id: str) -> Optional[dict]:
        return self._index.get(ku_id)

    # ══════════ 只读:临时规则统计 ══════════

    def count_temp_effects(self) -> int:
        """当前栈内未回滚的临时规则数(受 MAX_TEMP_RULES 限制)。"""
        with self._registry._lock:
            return sum(1 for e in self._registry._stack if e.batch_id and e.batch_id.startswith("temp:"))

    @staticmethod
    def generate_temp_uid(ts: float, seq: int) -> str:
        """生成临时规则 UID: TMP-<ts秒>-<seq三位补零>。"""
        return f"TMP-{int(ts):010d}-{seq:03d}"

    # ══════════ 内部:缓存一致性原语 ══════════

    def _replace(self, ku_id: str, ku: dict) -> None:
        """按 ku_id 就地替换;不存在则追加。cache 与 index 同步维护。"""
        for i, k in enumerate(self._cache):
            if k.get("ku_id") == ku_id:
                self._cache[i] = ku
                break
        else:
            self._cache.append(ku)
        self._index[ku_id] = ku

    def _delete(self, ku_id: str) -> None:
        self._cache[:] = [k for k in self._cache if k.get("ku_id") != ku_id]
        self._index.pop(ku_id, None)

    def _emit(self, name: str, apply, undo, batch_id, detail: str) -> Effect:
        """构造 Effect 并登记进注册表(apply 立即执行)。"""
        eff = Effect(name=name, apply=apply, undo=undo, batch_id=batch_id, detail=detail)
        self._registry.apply(eff)
        return eff

    def _mark_dirty_cb(self) -> None:
        """变更后统一标记索引过期(汇流性入口)。"""
        self._mark_dirty()

    # ══════════ 单条操作 ══════════

    def add_rule(self, ku: dict, batch_id: Optional[str] = None, temp: bool = False) -> Effect:
        """新增一条规则。undo=从缓存删除。

        temp=True: 临时规则——自动使用 TMP-<ts>-<seq> 命名,batch_id="temp:<ts>",
                   detail 标记"临时",受 MAX_TEMP_RULES 容量限制,重启/reload 即失。
        """
        ts = time.time()
        if temp:
            # 临时规则:强制 UID + 容量检查
            if batch_id and not batch_id.startswith("temp:"):
                batch_id = f"temp:{int(ts)}"
            elif not batch_id:
                batch_id = f"temp:{int(ts)}"
            self._temp_counter += 1
            ku_id = self.generate_temp_uid(ts, self._temp_counter)
            ku["ku_id"] = ku_id
            self._temp_rule_ids.add(ku_id)
            max_check = self.count_temp_effects()
            if max_check >= self._max_temp_rules:
                raise ValueError(
                    f"临时规则已达上限({self._max_temp_rules}条),无法创建第{max_check + 1}条。"
                    "请固化有效规则或回滚丢弃无效规则后再试。"
                )
            detail = f"[临时] 新增规则 {ku_id} · {ku.get('title', '')}"
        else:
            ku_id = ku.get("ku_id")
            if not ku_id:
                raise ValueError("规则缺少 ku_id 字段")
            if ku_id in self._index:
                raise ValueError(f"规则 {ku_id} 已存在,请用 update_rule")
            detail = f"新增规则 {ku_id} · {ku.get('title', '')}"

        ku = copy.deepcopy(ku)  # 防外部篡改

        def apply():
            self._replace(ku_id, ku)

        def undo():
            self._delete(ku_id)
            if temp:
                self._temp_rule_ids.discard(ku_id)

        eff = self._emit(
            f"rule:add:{ku_id}", apply, undo, batch_id,
            detail,
        )
        self._mark_dirty_cb()
        return eff

    def update_rule(self, ku_id: str, **patch) -> Effect:
        """更新一条规则(字段级补丁)。undo=恢复旧快照。"""
        if ku_id not in self._index:
            raise ValueError(f"规则 {ku_id} 不存在,请用 add_rule")
        old = copy.deepcopy(self._index[ku_id])
        new = copy.deepcopy(old)
        new.update(patch)

        def apply():
            self._replace(ku_id, new)

        def undo():
            self._replace(ku_id, old)

        eff = self._emit(
            f"rule:update:{ku_id}", apply, undo, None,
            f"更新规则 {ku_id}: {list(patch.keys())}",
        )
        self._mark_dirty_cb()
        return eff

    def remove_rule(self, ku_id: str, batch_id: Optional[str] = None) -> Effect:
        """删除一条规则。undo=恢复快照。"""
        if ku_id not in self._index:
            raise ValueError(f"规则 {ku_id} 不存在")
        old = copy.deepcopy(self._index[ku_id])

        def apply():
            self._delete(ku_id)

        def undo():
            self._replace(ku_id, old)

        eff = self._emit(
            f"rule:remove:{ku_id}", apply, undo, batch_id,
            f"删除规则 {ku_id} · {old.get('title', '')}",
        )
        self._mark_dirty_cb()
        return eff

    # ══════════ 批量加载 ══════════

    def load_batch(self, kus: List[dict], batch_id: Optional[str] = None, include_temp: bool = False) -> Effect:
        """批量加载(新增或覆盖,以 ku_id 为准)。

        include_temp=True: 批量标记为临时规则(batch_id="temp:<ts>")。
        undo=按逆序恢复全部快照 —— 复合逆自动派生:
        每条记录更新前快照,回滚时从后往前恢复,与施加顺序严格互逆。
        """
        ts = time.time()
        temp_uids_generated: List[str] = []  # 本次操作实际生成/使用的uid列表(用于undo清理)

        if include_temp:
            batch_id = batch_id or f"temp:{int(ts)}"
            # 先收集有效条目并生成新UID
            valid_kus = [k for k in kus if k.get("ku_id")]
            if not valid_kus:
                raise ValueError("批量加载列表为空或全部缺少 ku_id")
            # 容量检查
            if self.count_temp_effects() + len(valid_kus) > self._max_temp_rules:
                raise ValueError(
                    f"临时规则将超出上限({self._max_temp_rules}条):"
                    f"当前{self.count_temp_effects()}+新{len(valid_kus)}={self.count_temp_effects()+len(valid_kus)}"
                )
            # 遍历生成UID
            snapshots: List[tuple] = []
            for i, raw in enumerate(valid_kus):
                original_id = raw["ku_id"]
                seq = self._temp_counter + 1 + i  # 下一批序号
                uid = self.generate_temp_uid(ts, seq)
                temp_uids_generated.append(uid)
                raw_copy = copy.deepcopy(raw)
                raw_copy["ku_id"] = uid
                # 快照用原始ID查旧数据,但apply时用uid
                if original_id in self._index:
                    snapshots.append((uid, copy.deepcopy(self._index[original_id]), raw_copy))
                else:
                    snapshots.append((uid, None, raw_copy))
            self._temp_counter += len(valid_kus)
            self._temp_rule_ids.update(temp_uids_generated)
        else:
            batch_id = batch_id or f"{DEFAULT_BATCH_ID}_{int(time.time())}"
            valid_kus = [k for k in kus if k.get("ku_id")]
            if not valid_kus:
                raise ValueError("批量加载列表为空或全部缺少 ku_id")
            snapshots: List[tuple] = []
            for raw in valid_kus:
                ku_id = raw["ku_id"]
                if ku_id in self._index:
                    snapshots.append((ku_id, copy.deepcopy(self._index[ku_id]), copy.deepcopy(raw)))
                else:
                    snapshots.append((ku_id, None, copy.deepcopy(raw)))

        def apply():
            for uid, _old, ku in snapshots:
                self._replace(uid, ku)

        def undo():
            # 复合逆:逆序遍历快照
            for uid, old, _ku in reversed(snapshots):
                if old is None:
                    self._delete(uid)
                else:
                    self._replace(uid, old)
            if include_temp:
                for tid in temp_uids_generated:
                    self._temp_rule_ids.discard(tid)

        eff = self._emit(
            f"rule:batch:{batch_id}", apply, undo, batch_id,
            f"{'[临时] ' if include_temp else ''}批量加载 {len(snapshots)} 条(批次 {batch_id})",
        )
        self._mark_dirty_cb()
        return eff

    # ══════════ 持久化落盘(显式调用,非自动) ══════════

    def persist(self, all_ku_path, include_temp: bool = False) -> int:
        """把当前缓存写回 all_ku.json。

        include_temp=False(默认): 排除临时规则(batch_id 以"temp:"开头的Effect)写入磁盘。
        include_temp=True: 全部写入(用于固化后的显式落盘)。

        注意:热更新默认不落盘(汇流性);需要固化时才显式调用。
        调用前建议先备份原文件。
        """
        import json
        import os

        if not include_temp and self._registry is not None:
            # 直接从 _temp_rule_ids 取已生效的临时规则uid列表
            temp_kus = set(self._temp_rule_ids)
            # 兜底:也从 registry stack 补充（防止 _temp_rule_ids 与 stack 不同步）
            with self._registry._lock:
                for eff in self._registry._stack:
                    if eff.batch_id and eff.batch_id.startswith("temp:"):
                        parts = eff.name.split(":", 2)
                        if len(parts) >= 3:
                            temp_kus.add(parts[2])
            # 过滤 temp 规则
            write_cache = [k for k in self._cache if k.get("ku_id") not in temp_kus]
        else:
            write_cache = self._cache

        if os.path.exists(all_ku_path):
            backup = f"{all_ku_path}.bak"
            with open(all_ku_path, "r", encoding="utf-8") as f:
                with open(backup, "w", encoding="utf-8") as bf:
                    bf.write(f.read())
        with open(all_ku_path, "w", encoding="utf-8") as f:
            json.dump(write_cache, f, ensure_ascii=False, indent=1)
        return len(write_cache)
