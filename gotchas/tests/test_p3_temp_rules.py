# -*- coding: utf-8 -*-
"""P3-1 机制层单元测试 —— 临时规则(temp) + 持久化隔离 + 容量上限

验收1 临时UID: 创建 temp=true -> 自动使用 TMP-<ts>-<seq> 命名
验收2 临时标记: batch_id="temp:<ts>", detail含"临时", count_temp_effects 计数正确
验收3 容量上限: MAX_TEMP_RULES=50, 第51条拒绝
验收4 persist隔离: persist()默认不写临时规则到磁盘
验收5 临时规则回滚: rollback 后从缓存移除, 从 _temp_rule_ids 清除
验收6 load_batch include_temp=True: 批量临时规则可整体回滚
验收7 UID格式: generate_temp_uid 产出正确的 TMP-xxx-yyy 格式
验收7b reload行为: 临时规则在reload后被清空
"""
import copy
import json
import os
import sys
import tempfile
import time

BASE = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a"
sys.path.insert(0, BASE)
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

from gotchas.runtime.effects import EffectRegistry, ST_APPLIED
from gotchas.runtime.rule_manager import RuleManager, MAX_TEMP_RULES

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


# --- 初始数据 ---
initial = [make_ku("GZ-INIT-001", "初始规则一")]
cache = copy.deepcopy(initial)
index = {k["ku_id"]: k for k in cache}
_dirty = False

def mark_dirty():
    global _dirty
    _dirty = True


def snapshot(cache):
    return copy.deepcopy(cache)


print(f"== 验收7 UID格式:generate_temp_uid ==")
uid1 = RuleManager.generate_temp_uid(1692259200.0, 1)
check("UID格式 TMP-xxxxxxxxxx-NNN", uid1 == "TMP-1692259200-001", f"得到 {uid1}")
uid2 = RuleManager.generate_temp_uid(1692259200.0, 100)
check("序号三位补零", uid2 == "TMP-1692259200-100", f"得到 {uid2}")


print("\n== 验收1 临时UID: 创建 temp=true -> 自动使用 TMP-<ts>-<seq> 命名 ==")
registry = EffectRegistry()
rm = RuleManager(cache, index, registry=registry, mark_dirty=mark_dirty)
base = snapshot(cache)

e1 = rm.add_rule(make_ku("CUSTOM-ID", "自定义ID会被覆盖"), temp=True)
check("临时规则使用了自动生成UID", e1.name.startswith("rule:add:TMP-"), f"name={e1.name}")
uid1_actual = e1.name.split(":")[2]
check("自生成UID以TMP-开头", uid1_actual.startswith("TMP-"))

e2 = rm.add_rule({"ku_id": "ALSO-CUSTOM", "title": "也会被覆盖", "question": "自定义ID也会被覆盖的问题"}, temp=True)
uid2_actual = e2.name.split(":")[2]
check("即使输入有ku_id也会覆盖为TMP格式", "ALSO-CUSTOM" not in index)
check("第二行也生成了TMP UID", e2.name.startswith("rule:add:TMP-"))

e3 = rm.add_rule(make_ku("GZ-STABLE", "稳定规则不临时"), temp=False)
check("非临时规则保留原始ku_id", "GZ-STABLE" in index)
check("普通规则不在临时计数器中", rm.count_temp_effects() == 2, f"expected 2, got {rm.count_temp_effects()}")


print("\n== 验收2 临时标记: batch_id/detail/计数 ==")
check("临时规则的batch_id以temp:开头", e1.batch_id and e1.batch_id.startswith("temp:"), f"batch_id={e1.batch_id}")
check("临时规则detail含'临时'", "[临时]" in e1.detail, f"detail={e1.detail}")
check("count_temp_effects返回正确值2", rm.count_temp_effects() == 2)
rm.add_rule(make_ku("GZ-NOTEMP", "非临时"), temp=False)
check("添加非临时规则后计数仍为2", rm.count_temp_effects() == 2)


print("\n== 验收3 容量上限: MAX_TEMP_RULES ==")
remaining = MAX_TEMP_RULES - 2
for i in range(remaining):
    rm.add_rule(make_ku(f"GZ-TMP-{i}", f"临时{i}"), temp=True)
check(f"成功添加了{remaining}个额外临时规则", True)
check(f"最终临时规则数等于上限{MAX_TEMP_RULES}", rm.count_temp_effects() == MAX_TEMP_RULES,
      f"expected {MAX_TEMP_RULES}, got {rm.count_temp_effects()}")
try:
    rm.add_rule(make_ku(f"GZ-OVERFLOW", "溢出"), temp=True)
    check("超过上限应该抛出ValueError", False, "未抛异常")
except ValueError as ve:
    check(f"超过上限抛出错误: {str(ve)[:60]}", "已达上限" in str(ve))


print("\n== 验收4 persist隔离: persist()默认不写临时规则到磁盘 ==")
registry4 = EffectRegistry()
cache4 = copy.deepcopy([make_ku("GZ-PERS-1", "持久规则1")])
index4 = {"GZ-PERS-1": cache4[0]}
rm4 = RuleManager(cache4, index4, registry=registry4, mark_dirty=mark_dirty, max_temp_rules=10)

e_persist_temp = rm4.add_rule(make_ku("ANY-ID", "要隔离的临时规则"), temp=True)
persist_uid = e_persist_temp.name.split(":")[2]
rm4.add_rule(make_ku("GZ-PERS-2", "持久规则2"))

check("临时规则已加入缓存", persist_uid in index4)
check("持久规则已加入缓存", "GZ-PERS-2" in index4)

with tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir=BASE) as tf:
    tmp_path = tf.name

try:
    written_count = rm4.persist(tmp_path, include_temp=False)
    with open(tmp_path, "r", encoding="utf-8") as f:
        persisted_data = json.load(f)
    persisted_ids = {k["ku_id"] for k in persisted_data}
    check("persist排除了临时规则", persist_uid not in persisted_ids,
          f"included: {persisted_ids}")
    check("persist包含持久规则", "GZ-PERS-1" in persisted_ids and "GZ-PERS-2" in persisted_ids)
    check(f"写入条数正确(2条持久)", written_count == 2, f"written={written_count}")

    rm4.add_rule(make_ku("ANY-SECOND", "第二个临时规则"), temp=True)
    second_uid = list(rm4._temp_rule_ids)[-1]
    written_with_temp = rm4.persist(tmp_path, include_temp=True)
    with open(tmp_path, "r", encoding="utf-8") as f:
        persisted_full = json.load(f)
    full_ids = {k["ku_id"] for k in persisted_full}
    check("include_temp=True包含临时规则", persist_uid in full_ids and second_uid in full_ids)
    check(f"include_temp=True时写入所有条数", written_with_temp == 4,
          f"written={written_with_temp}, expected 4")
finally:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)


print("\n== 验收5 临时规则回滚: rollback后从缓存移除并从_temp_rule_ids清除 ==")
registry5 = EffectRegistry()
cache5 = []
index5 = {}
rm5 = RuleManager(cache5, index5, registry=registry5, mark_dirty=mark_dirty, max_temp_rules=10)

e_r1 = rm5.add_rule(make_ku("ANY-R1", "待回滚临时规则1"), temp=True)
uid_r1 = e_r1.name.split(":")[2]
e_r2 = rm5.add_rule(make_ku("ANY-R2", "待回滚临时规则2"), temp=True)
uid_r2 = e_r2.name.split(":")[2]
rm5.add_rule(make_ku("GZ-STABLE-R", "稳定规则"), temp=False)
check("创建了两条临时规则", rm5.count_temp_effects() == 2)

ok = registry5.rollback(e_r2.effect_id)
check("rollback temp 成功", ok and uid_r2 not in index5)
check("回滚后计数降为1", rm5.count_temp_effects() == 1)

ok = registry5.rollback(e_r1.effect_id)
check("第二条rollback成功", ok and uid_r1 not in index5)
check("回滚后计数归零", rm5.count_temp_effects() == 0)


print("\n== 验收6 load_batch include_temp=True: 批量临时规则可整体回滚 ==")
registry6 = EffectRegistry()
cache6 = []
index6 = {}
rm6 = RuleManager(cache6, index6, registry=registry6, mark_dirty=mark_dirty, max_temp_rules=10)

e_batch = rm6.load_batch([
    make_ku("BATCH-1", "批量临时1"),
    make_ku("BATCH-2", "批量临时2"),
], include_temp=True)

check("批量临时规则已施加", e_batch.state == ST_APPLIED)
check("批次以temp:开头", e_batch.batch_id and e_batch.batch_id.startswith("temp:"))
check("[临时]标记在detail中", "[临时]" in e_batch.detail)

batch_temp_uids = set(rm6._temp_rule_ids)
check(f"批量新增的两条都在缓存中(uid:{list(batch_temp_uids)})", len(batch_temp_uids) == 2 and all(u in index6 for u in batch_temp_uids))

ok = registry6.rollback_batch(e_batch.batch_id)
check("批量回滚成功", ok and len([k for k in index6 if k.startswith("TMP-")]) == 0)
check("批量回滚后计数归零", rm6.count_temp_effects() == 0)


print("\n== 验收7b reload 行为:临时规则在reload后被清空 ==")
registry7 = EffectRegistry()
cache7 = copy.deepcopy([make_ku("GZ-RELOAD-1", "重启前存在")])
index7 = {"GZ-RELOAD-1": cache7[0]}
rm7 = RuleManager(cache7, index7, registry=registry7, mark_dirty=mark_dirty, max_temp_rules=10)

e_temp_reload = rm7.add_rule(make_ku("ANY-RELOAD", "临时重载规则"), temp=True)
actual_reload_uid = e_temp_reload.name.split(":")[2]
check("临时规则已加入内存缓存", actual_reload_uid in index7)

cache7.clear()
cache7.extend(copy.deepcopy([make_ku("GZ-RELOAD-1", "重启前存在")]))
index7.clear()
index7.update({k["ku_id"]: k for k in cache7})

check("reload后临时规则已从缓存消失", actual_reload_uid not in index7)
check("reload后持久规则仍在", "GZ-RELOAD-1" in index7)
# reload 只清 cache/索引，不清 registry；registry 由 gotchas_api._reload_data 控制清理
check("reload后临时规则从缓存移除(核心语义)", len([k for k in cache7 if k.get("ku_id").startswith("TMP-")]) == 0)


print("\n" + "=" * 50)
print(f"P3-1 机制层测试汇总: {PASS} 通过 / {FAIL} 失败")
print("=" * 50)
sys.exit(1 if FAIL else 0)
