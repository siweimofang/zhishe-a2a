"""
HookManager 钩子管理器 (v0.1)
==============================
四个钩子点,与检索/回答链路对齐:
  PRE_SEARCH   检索前 —— 可改写 query、注入拦截(限流/探测)
  POST_SEARCH  检索后 —— 可改写 results(过滤/重排/注入补充)
  PRE_LLM      大模型调用前 —— 可改写 prompt、中止调用(abort)
  POST_LLM     大模型返回后 —— 可改写 answer(水印/脱敏)

余效应隔离:每个钩子声明 deps(依赖的服务/能力),依赖未就绪不激活。
余效应拦截:钩子即元数据层 —— 限流/探测/水印作为钩子挂载,跨切面生效,
          业务代码里不掺防护逻辑。

钩子注册本身是可逆副作用:register() 返回 Effect,
undo=注销该钩子 —— 钩子体系可被 EffectRegistry 整体回滚。
钩子执行异常只记日志,不中断主链路(钩子失败不炸业务)。
"""

import enum
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .effects import Effect, EffectRegistry

log = logging.getLogger("gotchas.runtime.hooks")


class HookPoint(str, enum.Enum):
    """钩子点枚举(与检索/回答链路一一对应)。"""

    PRE_SEARCH = "pre_search"
    POST_SEARCH = "post_search"
    PRE_LLM = "pre_llm"
    POST_LLM = "post_llm"


@dataclass
class Hook:
    """一个已注册的钩子。"""

    point: HookPoint
    fn: Callable[[Dict], None]          # fn(ctx),ctx 为 dict,就地修改
    deps: List[str] = field(default_factory=list)   # 依赖服务名,未就绪不激活
    enabled: bool = True
    name: str = ""
    hook_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class HookManager:
    """钩子管理器:register 登记(返回 Effect),run 按序执行。"""

    def __init__(
        self,
        registry: Optional[EffectRegistry] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._hooks: Dict[HookPoint, List[Hook]] = {p: [] for p in HookPoint}
        self._by_id: Dict[str, Hook] = {}
        self._registry = registry or EffectRegistry()
        self._services: Dict[str, Any] = dict(services or {})
        self._lock = threading.RLock()

    # ══════════ 依赖服务管理(余效应隔离) ══════════

    def set_services(self, services: Dict[str, Any]) -> None:
        """注入/更新依赖服务集合(如 {"guard": guard_module})。"""
        with self._lock:
            self._services.update(services)

    def service_ready(self, dep: str) -> bool:
        """依赖是否就绪(服务存在且非 None)。"""
        with self._lock:
            return dep in self._services and self._services[dep] is not None

    def service_status(self) -> Dict[str, bool]:
        with self._lock:
            return {k: v is not None for k, v in self._services.items()}

    # ══════════ 注册/注销 ══════════

    def register(
        self,
        point: HookPoint,
        fn: Callable[[Dict], None],
        deps: Optional[List[str]] = None,
        name: str = "",
    ) -> Effect:
        """注册一个钩子。返回 Effect(undo=注销该钩子)。

        已登记进注册表 —— 钩子体系可被整体回滚/卸载。
        返回的 Effect 即注册表内登记的对象(apply 已执行,undo=注销)。
        """
        hook = Hook(
            point=HookPoint(point),
            fn=fn,
            deps=list(deps or []),
            name=name or getattr(fn, "__name__", "anonymous"),
        )

        def apply():
            with self._lock:
                self._hooks[hook.point].append(hook)
                self._by_id[hook.hook_id] = hook

        def undo():
            with self._lock:
                self._hooks[hook.point] = [h for h in self._hooks[hook.point] if h.hook_id != hook.hook_id]
                self._by_id.pop(hook.hook_id, None)

        eff = Effect(
            name=f"hook:{hook.name}",
            apply=apply,
            undo=undo,
            detail=f"钩子 {hook.name} @ {hook.point.value}",
            protected=True,  # 系统级:整体回滚默认保留,单条回滚可精确注销
        )
        self._registry.apply(eff)
        return eff

    def unregister(self, hook_id: str) -> bool:
        """直接注销钩子(不走注册表,幂等)。"""
        with self._lock:
            hook = self._by_id.pop(hook_id, None)
            if not hook:
                return False
            self._hooks[hook.point] = [h for h in self._hooks[hook.point] if h.hook_id != hook_id]
            return True

    def set_enabled(self, hook_id: str, enabled: bool) -> bool:
        with self._lock:
            hook = self._by_id.get(hook_id)
            if not hook:
                return False
            hook.enabled = enabled
            return True

    def hooks(self, point: Optional[HookPoint] = None) -> List[Hook]:
        with self._lock:
            if point is None:
                return [h for p in HookPoint for h in self._hooks[p]]
            return list(self._hooks.get(HookPoint(point), []))

    # ══════════ 执行 ══════════

    def run(self, point: HookPoint, ctx: Dict) -> Dict:
        """执行该钩子点的全部可用钩子(按注册序)。

        - enabled=False 跳过
        - deps 未全部就绪 → 跳过(余效应隔离)
        - 钩子异常 → 记日志,继续执行后续钩子(隔离,不炸主链路)
        返回原 ctx(钩子就地修改)。
        """
        with self._lock:
            hooks = list(self._hooks.get(HookPoint(point), []))
        for hook in hooks:
            if not hook.enabled:
                continue
            if not all(self.service_ready(d) for d in hook.deps):
                continue
            try:
                hook.fn(ctx)
            except Exception as exc:  # noqa: BLE001
                log.warning("钩子执行失败 [%s] @ %s: %s", hook.name, point.value, exc)
        return ctx
