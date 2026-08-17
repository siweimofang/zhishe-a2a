"""
gotchas.runtime —— 可逆副作用运行时 (v0.1)
============================================
情报-15(DSH论文)在 Gotchas 引擎的工程落地:

- effects.py       EffectRegistry 逆函数累加器(可逆副作用账本,UNLOADING 两阶段)
- rule_manager.py  规则热更新管理器(汇流性:只改缓存+标记dirty,批量加载可整体回滚)
- hooks.py         钩子管理器(四钩子点,guard 三件套以钩子接入)

设计文档:docs/Gotchas引擎可逆副作用实现方案_v0.1.md
"""

from .effects import (
    Effect,
    EffectRegistry,
    ST_PENDING,
    ST_APPLIED,
    ST_ROLLED_BACK,
    ST_SKIPPED,
    ST_FAILED,
    UN_R1,
    UN_R2,
)
from .hooks import Hook, HookManager, HookPoint
from .rule_manager import RuleManager

__all__ = [
    "Effect",
    "EffectRegistry",
    "Hook",
    "HookManager",
    "HookPoint",
    "RuleManager",
    "ST_PENDING",
    "ST_APPLIED",
    "ST_ROLLED_BACK",
    "ST_SKIPPED",
    "ST_FAILED",
    "UN_R1",
    "UN_R2",
]
