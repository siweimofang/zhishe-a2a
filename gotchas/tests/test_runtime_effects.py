# -*- coding: utf-8 -*-
"""可逆副作用运行时 v0.1 单元测试 —— 5条验收标准

验收1 可逆性:   单条操作(add/update/remove)回滚后缓存复原
验收2 复合逆:   批量加载整体回滚(逆序恢复快照)
验收3 汇流性:   变更只改缓存+标记dirty,检索前幂等重建,整体回滚复原
验收4 UNLOADING:R1 拒收新副作用 / R2 带守卫回滚(guard=False 保留)
验收5 零破坏:   钩子异常隔离不炸主流程 / guard 拦截不生效 / 幂等回滚
"""
import copy
import sys

BASE = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a"
sys.path.insert(0, BASE)
if __name__ == "__main__":
    # 仅直接运行时启用 UTF-8 输出;pytest 收集 import 时不执行,避免捕获冲突
    sys.stdout.reconfigure(encoding="utf-8")

from gotchas.runtime.effects import (
    Effect, EffectRegistry,
    ST_APPLIED, ST_ROLLED_BACK, ST_SKIPPED, UN_R1,
)
from gotchas.runtime.rule_manager import RuleManager
from gotchas.runtime.hooks import HookManager, HookPoint

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [通过] {name}")
    else:
        FAIL += 1
        print(f"  [失败] {name}  -- {detail}")


def snapshot(cache):
    return copy.deepcopy(cache)


def make_ku(ku_id, title, **extra):
    ku = {
        "ku_id": ku_id, "title": title,
        "question": f"{title}的具体问题是什么情况",  # ≥8字,满足窄规则校验
        "stage": "STAGE_02",
        "severity": "SEV_MEDIUM", "knowledge_type": "gotcha",
        "description": f"{title}的描述", "how_to_avoid": f"{title}的正确做法",
        "typical_scenario": f"{title}场景", "trigger_keywords": [title],
        "trade": ["TRADE_DESIGN"], "role": ["ROLE_DESIGNER"],
        "scope": "universal", "causal_chain": [], "related_ku_ids": [],
        "metadata": {},
    }
    ku.update(extra)
    return ku


# ── 初始数据(模拟 all_ku 结构) ──
initial = [make_ku("GZ-TEST-001", "初始规则一"), make_ku("GZ-TEST-002", "初始规则二")]
cache = copy.deepcopy(initial)
index = {k["ku_id"]: k for k in cache}
_dirty = False


def mark_dirty():
    global _dirty
    _dirty = True


print("== 验收1 可逆性:单条操作回滚 ==")
registry = EffectRegistry()
rm = RuleManager(cache, index, registry=registry, mark_dirty=mark_dirty)
base = snapshot(cache)

e1 = rm.add_rule(make_ku("GZ-TEST-003", "新增规则"))
check("add_rule 已施加且进缓存", e1.state == ST_APPLIED and "GZ-TEST-003" in index)
check("add_rule 已标记 dirty", _dirty is True)
_dirty = False
ok = registry.rollback(e1.effect_id)
check("rollback(add) 成功", ok and "GZ-TEST-003" not in index and e1.state == ST_ROLLED_BACK)
check("回滚后缓存复原", snapshot(cache) == base)

e2 = rm.update_rule("GZ-TEST-001", title="更新后的标题", severity="SEV_HIGH")
check("update_rule 已施加", index["GZ-TEST-001"]["title"] == "更新后的标题")
ok = registry.rollback(e2.effect_id)
check("rollback(update) 恢复旧快照",
      index["GZ-TEST-001"]["title"] == "初始规则一" and index["GZ-TEST-001"]["severity"] == "SEV_MEDIUM")

e3 = rm.remove_rule("GZ-TEST-002")
check("remove_rule 已施加", "GZ-TEST-002" not in index)
ok = registry.rollback(e3.effect_id)
check("rollback(remove) 恢复快照",
      "GZ-TEST-002" in index and index["GZ-TEST-002"]["title"] == "初始规则二")
check("三轮操作后缓存完全复原", snapshot(cache) == base)

print("== 验收2 复合逆:批量加载整体回滚 ==")
registry = EffectRegistry()
rm = RuleManager(cache, index, registry=registry, mark_dirty=mark_dirty)
base = snapshot(cache)
e_batch = rm.load_batch([
    make_ku("GZ-TEST-004", "批量新增四"),
    make_ku("GZ-TEST-005", "批量新增五"),
    make_ku("GZ-TEST-001", "批量覆盖一"),   # 覆盖已存在条目
], batch_id="b_alpha")
check("batch 已施加(新增+覆盖混合)",
      index["GZ-TEST-001"]["title"] == "批量覆盖一"
      and "GZ-TEST-004" in index and "GZ-TEST-005" in index)
ok = registry.rollback_batch("b_alpha")
check("rollback_batch 成功", ok)
check("批量回滚后缓存完全复原", snapshot(cache) == base)

print("== 验收3 汇流性:多次操作整体回滚 + 幂等重建 ==")
registry = EffectRegistry()
rm = RuleManager(cache, index, registry=registry, mark_dirty=mark_dirty)
base = snapshot(cache)
rm.add_rule(make_ku("GZ-TEST-006", "六"), batch_id="b_x")
rm.update_rule("GZ-TEST-001", title="改一")
rm.remove_rule("GZ-TEST-002")
rm.add_rule(make_ku("GZ-TEST-007", "七"))
check("四连操作后 dirty 已标记", _dirty is True)
result = registry.rollback_all()
check("rollback_all 全成功", result["ok"] and not result["failed"] and not result["skipped"])
check("整体回滚后缓存完全复原", snapshot(cache) == base)
check("注册表栈已清空", registry.size == 0)

class FakeSearcher:
    """模拟 GotchasHybrid:set_data 内存直通 + build_index 幂等重建"""
    def __init__(self):
        self.rebuilds = 0
        self.data = None
    def set_data(self, d):
        self.data = d
    def build_index(self):
        self.rebuilds += 1

fake = FakeSearcher()
_dirty = True
if _dirty:          # 模拟 gotchas_api._ensure_index()
    fake.set_data(cache)
    fake.build_index()
    _dirty = False
check("检索前重建一次,数据源=当前缓存", fake.rebuilds == 1 and fake.data is cache)
if _dirty:          # 无变更不重建
    fake.set_data(cache)
    fake.build_index()
    _dirty = False
check("无变更不重复重建", fake.rebuilds == 1)

print("== 验收4 UNLOADING 守卫:R1 拒收 / R2 带守卫回滚 ==")
registry = EffectRegistry()
rm = RuleManager(cache, index, registry=registry, mark_dirty=mark_dirty)
e1 = rm.add_rule(make_ku("GZ-TEST-008", "八"))
registry.begin_unload()
check("R1 进入卸载态", registry.unloading == UN_R1)
e2 = rm.add_rule(make_ku("GZ-TEST-009", "九"))
check("R1 拒收新副作用", e2.state == ST_SKIPPED and "GZ-TEST-009" not in index)
registry.cancel_unload()
e3 = rm.add_rule(make_ku("GZ-TEST-009", "九"))
check("取消卸载后恢复受理", e3.state == ST_APPLIED and "GZ-TEST-009" in index)
e3.guard = lambda: False   # 模拟"不可回滚"的副作用(如外部依赖)
result = registry.finish_unload()
check("R2 守卫拦截保留该项", "GZ-TEST-009" in index and e3.effect_id in result["skipped"])
check("R2 其余副作用已回滚", "GZ-TEST-008" not in index)
check("R2 后恢复受理", registry.unloading is None)

print("== 验收5 零破坏:钩子异常隔离 / 依赖隔离 / guard 拦截 / 幂等 ==")
registry = EffectRegistry()
hm = HookManager(registry=registry, services={"svc": object()})
calls = []

def good(ctx):
    calls.append("good")
    ctx["marker"] = 1

def bad(ctx):
    raise RuntimeError("钩子炸了")

def lazy(ctx):
    calls.append("lazy")

hm.register(HookPoint.PRE_SEARCH, good, name="good")
hm.register(HookPoint.PRE_SEARCH, bad, name="bad")
hm.register(HookPoint.PRE_SEARCH, lazy, deps=["missing_service"], name="lazy")

ctx = {"query": "测试"}
hm.run(HookPoint.PRE_SEARCH, ctx)
check("正常钩子执行且可改 ctx", "good" in calls and ctx.get("marker") == 1)
check("异常钩子被隔离,后续钩子继续", calls.count("good") == 1)
check("依赖未就绪的钩子不激活", "lazy" not in calls)

eff = hm.register(HookPoint.POST_SEARCH, lambda c: calls.append("ps"), name="ps")
hm.run(HookPoint.POST_SEARCH, {})
check("POST_SEARCH 钩子生效", "ps" in calls)
registry.rollback(eff.effect_id)
hm.run(HookPoint.POST_SEARCH, {})
check("回滚后钩子已注销(undo=注销)", calls.count("ps") == 1)

registry2 = EffectRegistry()
counter = {"n": 0}
eff_g = Effect(
    name="guard_test",
    apply=lambda: counter.__setitem__("n", counter["n"] + 1),
    undo=lambda: counter.__setitem__("n", counter["n"] - 1),
    guard=lambda: False,
)
ok = registry2.apply(eff_g)
check("guard=False 副作用未施加", not ok and counter["n"] == 0 and eff_g.state == ST_SKIPPED)

eff_x = Effect(name="x", apply=lambda: None, undo=lambda: None)
registry2.apply(eff_x)
registry2.rollback(eff_x.effect_id)
check("重复回滚幂等", registry2.rollback(eff_x.effect_id) is True)
check("回滚不存在的 effect 返回 False", registry2.rollback("nope") is False)

evs = registry.history(50)
check("事件日志已记录(applied/rolled_back)", any(e["event"] == "applied" for e in evs))

print("== 验收5b 系统级保护:整体回滚不误杀防护钩子 ==")
registry3 = EffectRegistry()
hm3 = HookManager(registry=registry3, services={})
calls3 = []
hm3.register(HookPoint.PRE_SEARCH, lambda c: calls3.append("g"), name="g1")
# 业务副作用与钩子共存
eff_biz = Effect(name="biz_op", apply=lambda: calls3.append("biz"), undo=lambda: None)
registry3.apply(eff_biz)
result = registry3.rollback_all()
check("rollback_all 保留系统钩子", len(hm3.hooks(HookPoint.PRE_SEARCH)) == 1)
check("rollback_all 清掉了业务副作用",
      eff_biz.state == "ROLLED_BACK" and registry3.size == 1)
check("返回中提示保留项", eff_biz.effect_id not in result["skipped"] and len(result["skipped"]) == 1)
hm3.run(HookPoint.PRE_SEARCH, {})
check("保留的钩子仍可执行", calls3.count("g") == 1)
# 精确回滚可注销钩子
hook_eff = registry3.applied_effects()[-1]
registry3.rollback(hook_eff.effect_id)
check("单条 rollback 可注销钩子", len(hm3.hooks(HookPoint.PRE_SEARCH)) == 0)
# force 可整体清除
registry3.apply(eff_biz)
hm3.register(HookPoint.PRE_SEARCH, lambda c: None, name="g2")
result = registry3.rollback_all(force=True)
check("force=True 连系统钩子一并清除", len(hm3.hooks(HookPoint.PRE_SEARCH)) == 0 and registry3.size == 0)

print("== 附加:重载后 RuleManager 引用稳定 ==")
registry = EffectRegistry()
rm = RuleManager(cache, index, registry=registry, mark_dirty=mark_dirty)
cache.clear()       # 模拟 gotchas_api._reload_data:clear+extend 就地重载
cache.extend(copy.deepcopy([make_ku("GZ-TEST-100", "重载后的数据")]))
index.clear()
index.update({k["ku_id"]: k for k in cache})
e = rm.add_rule(make_ku("GZ-TEST-101", "重载后新增"))
check("重载后仍可操作", "GZ-TEST-101" in index and registry.size == 1)
registry.rollback(e.effect_id)
check("重载后仍可回滚", "GZ-TEST-101" not in index and registry.size == 0)

print()
print(f"===== 汇总:{PASS} 通过 / {FAIL} 失败 =====")
sys.exit(1 if FAIL else 0)
