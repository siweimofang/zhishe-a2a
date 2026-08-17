"""
EffectRegistry 逆函数累加器 (v0.1)
====================================
情报-15(DSH论文)的工程落地:副作用建模为 Γ→Γ×(Γ→Γ)。
副作用在施加的同时把逆函数(undo)写进账本,回滚时按 LIFO 逆序执行,
复合逆自动派生 —— 先回滚后施加的,再回滚先施加的。

本模块只负责"副作用账本",不关心业务数据:
- Effect:一个可逆副作用(apply 施加 / undo 逆函数 / guard 施加守卫)
- EffectRegistry:LIFO 累加器(线程安全,历史事件日志)
- UNLOADING 两阶段:R1 停止受理新副作用 → R2 带守卫回滚

汇流性(Confluence):最终状态只取决于当前数据缓存,与操作历史无关。
业务侧(RuleManager)变更只改缓存+标记dirty,检索前幂等重建 ——
本注册表只保证"改坏了能退回来",不参与数据一致性的最终裁决。
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# ── 副作用状态机 ──
ST_PENDING = "PENDING"            # 已登记,未施加
ST_APPLIED = "APPLIED"            # 已施加(在栈中)
ST_ROLLED_BACK = "ROLLED_BACK"    # 已回滚(幂等:重复回滚无害)
ST_SKIPPED = "SKIPPED"            # guard 拦截或 UNLOADING 拒收,未施加
ST_FAILED = "FAILED"              # 施加或回滚时抛异常(账本保留,便于审计)

# ── UNLOADING 阶段 ──
UN_NONE = None
UN_R1 = "R1_STOP_ACCEPT"          # R1:停止受理新副作用(对外只读)
UN_R2 = "R2_GUARDED_ROLLBACK"     # R2:带守卫回滚全部已施加副作用


@dataclass
class Effect:
    """一个可逆副作用。

    apply: 施加动作(无参可调用,现场执行)
    undo:  逆函数(无参可调用,回滚时执行)
    guard: 施加守卫(返回 False 则本次施加被跳过,副作用不生效)
    batch_id: 批次归属(批量加载/批量回滚用)
    protected: 系统级保护(如防护钩子)。rollback_all 默认跳过,
               避免运维整体回滚误杀系统能力;单条 rollback(effect_id)
               不受限 —— 明确指定即可精确回滚。
    """
    name: str
    apply: Callable[[], Any]
    undo: Callable[[], Any]
    guard: Callable[[], bool] = field(default=lambda: True)
    batch_id: Optional[str] = None
    detail: str = ""
    protected: bool = False
    effect_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = field(default=ST_PENDING)
    created_at: float = field(default_factory=time.time)


class EffectRegistry:
    """LIFO 逆函数累加器(线程安全)。"""

    def __init__(self) -> None:
        self._stack: List[Effect] = []          # 已施加副作用,LIFO
        self._by_id: Dict[str, Effect] = {}     # 快查(含已回滚,保审计)
        self._history: List[Dict] = []          # 事件日志(最近2000条)
        self._unloading: Optional[str] = None   # None / R1 / R2
        self._lock = threading.RLock()

    # ══════════ 只读视图 ══════════

    @property
    def unloading(self) -> Optional[str]:
        return self._unloading

    @property
    def size(self) -> int:
        """当前栈内已施加未回滚的副作用数。"""
        with self._lock:
            return len(self._stack)

    def get(self, effect_id: str) -> Optional[Effect]:
        return self._by_id.get(effect_id)

    def applied_effects(self) -> List[Effect]:
        with self._lock:
            return list(self._stack)

    def history(self, limit: int = 200) -> List[Dict]:
        """事件日志(新的在前)。"""
        with self._lock:
            return list(reversed(self._history[-limit:]))

    # ══════════ 施加 ══════════

    def apply(self, effect: Effect, force: bool = False) -> bool:
        """施加一个副作用。成功 → True。

        - UNLOADING-R1 期间拒绝新副作用(force=True 可绕过,仅供系统内部兜底)
        - guard() 返回 False → 跳过,记 SKIPPED(不报错,调用方自行决定)
        - apply() 抛异常 → 记 FAILED,返回 False
        """
        with self._lock:
            if self._unloading == UN_R1 and not force:
                effect.state = ST_SKIPPED
                self._log("apply_rejected_unloading", effect, "UNLOADING-R1:停止受理新副作用")
                return False
            if effect.effect_id in self._by_id:
                self._log("apply_duplicate", effect, "effect_id 已存在,拒绝重复施加")
                return False
            if not force and not effect.guard():
                effect.state = ST_SKIPPED
                self._log("apply_skipped_guard", effect, "guard 拦截,副作用未生效")
                return False
            try:
                effect.apply()
            except Exception as exc:  # noqa: BLE001
                effect.state = ST_FAILED
                self._log("apply_failed", effect, str(exc))
                return False
            effect.state = ST_APPLIED
            self._by_id[effect.effect_id] = effect
            self._stack.append(effect)
            self._log("applied", effect)
            return True

    # ══════════ 回滚 ══════════

    def rollback(self, effect_id: str) -> bool:
        """回滚指定副作用(LIFO 语义)。

        目标上方的副作用必须先回滚(它们可能依赖目标),因此一并回滚。
        已回滚/未施加 → 幂等成功。undo 抛异常 → 记 FAILED 返回 False。
        """
        with self._lock:
            if effect_id not in self._by_id:
                self._log("rollback_miss", None, f"找不到 effect_id={effect_id}")
                return False
            target = self._by_id[effect_id]
            if target.state != ST_APPLIED:
                return True  # 幂等
            idx = next(i for i, e in enumerate(self._stack) if e.effect_id == effect_id)
            ok = True
            while len(self._stack) > idx:
                top = self._stack.pop()
                try:
                    top.undo()
                    top.state = ST_ROLLED_BACK
                    self._log("rolled_back", top)
                except Exception as exc:  # noqa: BLE001
                    top.state = ST_FAILED
                    self._log("rollback_failed", top, str(exc))
                    ok = False
            return ok

    def rollback_batch(self, batch_id: str) -> bool:
        """回滚某个批次全部副作用(按栈序,复合逆)。"""
        with self._lock:
            ids = [e.effect_id for e in self._stack if e.batch_id == batch_id]
            ok = True
            for eid in ids:
                if not self.rollback(eid):
                    ok = False
            self._log("rollback_batch", None, f"batch_id={batch_id} 目标{len(ids)}条")
            return ok

    def rollback_all(self, guarded: bool = False, force: bool = False) -> Dict:
        """回滚栈内全部副作用。

        guarded=False:一律回滚(忽略 guard)。
        guarded=True:带守卫回滚 —— guard() 为 False 的副作用保留
        在 _by_id(标记 SKIPPED),移出栈,返回 skipped 列表供人工处理。
        protected=True 的系统级副作用默认跳过(force=True 才连根清除),
        防止整体回滚误杀防护钩子等系统能力。
        """
        with self._lock:
            failed: List[str] = []
            skipped: List[str] = []
            keep: List[Effect] = []
            while self._stack:
                top = self._stack.pop()
                if top.protected and not force:
                    keep.append(top)  # 保留:回滚结束后压回栈(状态仍 APPLIED)
                    skipped.append(top.effect_id)
                    self._log("rollback_skipped_protected", top, "系统级副作用,整体回滚跳过")
                    continue
                if guarded and not top.guard():
                    top.state = ST_SKIPPED
                    skipped.append(top.effect_id)
                    self._log("rollback_skipped_guard", top, "守卫拦截,保留待人工处理")
                    continue
                try:
                    top.undo()
                    top.state = ST_ROLLED_BACK
                    self._log("rolled_back", top)
                except Exception as exc:  # noqa: BLE001
                    top.state = ST_FAILED
                    failed.append(top.effect_id)
                    self._log("rollback_failed", top, str(exc))
            for k in reversed(keep):  # 按原相对顺序压回
                self._stack.append(k)
            return {"ok": not failed and not skipped, "failed": failed, "skipped": skipped}

    # ══════════ UNLOADING 两阶段(卸载/下线守卫) ══════════

    def begin_unload(self) -> bool:
        """R1:进入卸载态,拒绝一切新副作用(对外表现为只读)。"""
        with self._lock:
            if self._unloading is not None:
                return False
            self._unloading = UN_R1
            self._log("unload_r1", None, "停止受理新副作用")
            return True

    def finish_unload(self) -> Dict:
        """R2:带守卫回滚全部已施加副作用,随后恢复受理。"""
        with self._lock:
            result = self.rollback_all(guarded=True)
            self._unloading = UN_NONE
            self._log("unload_r2", None, f"带守卫回滚完成:{result}")
            return result

    def cancel_unload(self) -> bool:
        """取消卸载(R1 阶段可撤回,已施加副作用不动)。"""
        with self._lock:
            if self._unloading == UN_R1:
                self._unloading = UN_NONE
                self._log("unload_cancelled", None, "取消卸载,恢复受理")
                return True
            return False

    # ══════════ 内部 ══════════

    def _log(self, event: str, effect: Optional[Effect], detail: str = "") -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "effect_id": effect.effect_id if effect else "",
            "name": effect.name if effect else "",
            "batch_id": effect.batch_id if effect else "",
            "state": effect.state if effect else "",
            "detail": detail,
        }
        self._history.append(entry)
        if len(self._history) > 2000:  # 上限防内存膨胀
            self._history = self._history[-2000:]
