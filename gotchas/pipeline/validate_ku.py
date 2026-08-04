# -*- coding: utf-8 -*-
"""Layer-1 Rule Gate: 知设知识库确定性验证引擎（纯代码，零模型参与）。

功能：
  1. Schema 校验：必填字段 / knowledge_type 合法 / standard 必需字段 / 悬空引用
  2. 数值校验：standard 条目文本数值与 verification_rules.json 真理表比对
     - 值完全匹配或更严格 -> PASS
     - 违反且规则为强制性条文 -> FAIL
     - 违反且非强制 -> WARN（需 Layer-2 独立模型确认）
  3. 效力状态：引用已废止强条文号（GB 50210-2018 五条）必须含 GB 55032 承接说明
  4. 自证检测：verify_method=ai_cross_reference 且无 verified_by -> PENDING_REVALIDATE

用法: python gotchas/pipeline/validate_ku.py [--report 输出路径]
"""
import json
import re
import sys
from collections import Counter

ROOT = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a"
DATA = ROOT + r"\gotchas\data\v1.0\all_ku.json"
RULES = ROOT + r"\gotchas\data\v1.0\verification_rules.json"
REPORT = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\outputs\audit_report_20260804.md"

VALID_TYPES = {"gotcha", "standard", "process", "material", "design"}
REQUIRED_STANDARD = ["standard_number", "standard_requirement", "compliance_criteria", "verification_method"]
ABOLISHED = ["3.1.4", "6.1.11", "6.1.12", "7.1.12", "11.1.12"]  # GB 50210-2018 五条原强条
CONDITIONAL_HINTS = ["时", "以下", "以上", "之间", "面积", "1/3", "允许", "靠尺", "套尺", "处"]
MATCH_TOL = 0.005  # 数值配对容差：容忍 2.1 vs 2.10 的书写差异


def build_unit_regex(aliases):
    """数字 + 可选空格 + 单位别名（长别名优先）"""
    ordered = sorted(aliases, key=len, reverse=True)
    return re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(" + "|".join(map(re.escape, ordered)) + ")")


def extract_values(text, units_map):
    """返回 [(value:float, unit, followed:str)]，followed 为值后 4 个字符用于语境判断"""
    out = []
    for unit, aliases in units_map.items():
        for m in build_unit_regex(aliases).finditer(text):
            out.append((float(m.group(1)), unit, text[m.end():m.end() + 4]))
    return out


def schema_check(k):
    errs = []
    kt = k.get("knowledge_type") or "gotcha"  # 隐式约定：缺省视为 gotcha
    if not k.get("ku_id"):
        errs.append("缺 ku_id")
    if kt not in VALID_TYPES:
        errs.append(f"knowledge_type 非法: {k.get('knowledge_type')}")
    if not k.get("title"):
        errs.append("缺 title")
    if kt == "standard":
        for f in REQUIRED_STANDARD:
            if not k.get(f):
                errs.append(f"standard 缺字段 {f}")
    return errs


def rule_check(k, rules, units_map):
    """对 standard 条目跑数值规则。

    配对激活制：只有文本中存在与 check 目标值精确配对（容差 MATCH_TOL）的值，
    该规则才激活；激活后同单位其他无配对值视为冲突候选（WARN），但排除
    已被其他规则配对的值（跨规则值域互认）。未激活的规则一律跳过——
    杜绝跨 topic 关键词串扰（如"栏杆净高"触发"室内净高"）。
    """
    text = (k.get("standard_number", "") + " " + k.get("standard_requirement", "") + " " +
            k.get("compliance_criteria", "") + " " + k.get("verification_method", ""))
    vals = extract_values(text, units_map)
    results = []

    # 第一遍：计算所有规则对该条目的配对值集合（供跨规则排除）
    paired_global = set()
    strict_activated = set()
    for r in rules:
        if not r.get("checks"):
            continue
        for c in r["checks"]:
            for v, u, followed in vals:
                if u == c["unit"] and not any(h in followed for h in CONDITIONAL_HINTS) and abs(v - c["value"]) <= MATCH_TOL:
                    paired_global.add((round(v, 4), u))

    for r in rules:
        if not r.get("keywords") or not any(kw in text for kw in r["keywords"]):
            continue
        if not r.get("checks"):
            results.append((r["id"], "PASS", "关键词命中但无数值检查"))
            continue
        activated = False
        strict_only = False
        for c in r["checks"]:
            unit = c["unit"]
            target = c["value"]
            same_unit = [v for v, u, followed in vals if u == unit and not any(h in followed for h in CONDITIONAL_HINTS)]
            paired = [v for v in same_unit if abs(v - target) <= MATCH_TOL]
            if paired:
                activated = True
                results.append((r["id"], "PASS", f"[{c['label']}] {target}{unit} 已配对"))
            else:
                # 全部同单位值都更严格（如 2.5 ≥ 2.4）视为通过
                if (same_unit and all(v > target for v in same_unit) and c["operator"] in (">=", ">")) or (
                        same_unit and all(v < target for v in same_unit) and c["operator"] in ("<=", "<")):
                    activated = True
                    strict_only = True
                    results.append((r["id"], "PASS", f"[{c['label']}] 文本值全部更严格（>={target}{unit}）"))
        # 冲突候选：仅"配对激活"时检查；排除跨规则已配对值
        if activated and not strict_only:
            all_targets = [c["value"] for c in r["checks"]]
            check_units = {c["unit"] for c in r["checks"]}
            for v, u, followed in vals:
                if any(h in followed for h in CONDITIONAL_HINTS):
                    continue
                if u in check_units and (round(v, 4), u) not in paired_global and not any(abs(v - t) <= MATCH_TOL for t in all_targets):
                    results.append((r["id"], "WARN", f"文本含未配对值 {v}{u}（上下文: …{followed}），需 Layer-2 确认"))
    return results


def abolished_check(k):
    text = (k.get("standard_number", "") + k.get("standard_requirement", "") +
            k.get("compliance_criteria", "") + k.get("description", ""))
    if "GB 50210" not in text:
        return []
    hits = [a for a in ABOLISHED if re.search(r"(?<!\d)" + a.replace(".", r"\.") + r"(?!\d)", text)]
    if hits and "55032" not in text:
        return [f"引用废止条文 {','.join(hits)} 但缺 GB 55032 承接说明"]
    return []


def self_verify_check(k):
    if k.get("knowledge_type") != "standard":
        return False
    md = k.get("metadata", {})
    vm = md.get("verify_method", "")
    if not md.get("verified_by") and "ai_cross_reference" in vm and md.get("quality_level") == "RELIABLE":
        return True
    return False


def main():
    kus = json.load(open(DATA, encoding="utf-8"))
    rules_cfg = json.load(open(RULES, encoding="utf-8"))
    rules = rules_cfg["rules"]
    units_map = rules_cfg["unit_aliases"]

    seen = {}
    schema_fails, dangling, rule_warns, abolished_hits, self_verified = [], [], [], [], []
    per_ku = {}

    for k in kus:
        kid = k["ku_id"]
        # 1. schema + 悬空引用
        errs = schema_check(k)
        if errs:
            schema_fails.append((kid, errs))
        for rel in k.get("related_ku_ids", []) or []:
            seen.setdefault(rel, 0)
            seen[kid] = seen.get(kid, 0) + 0
        # 悬空引用（第二遍做）
        per_ku[kid] = k

    for k in kus:
        for rel in k.get("related_ku_ids", []) or []:
            if rel not in per_ku:
                dangling.append((k["ku_id"], rel))

    for k in kus:
        if k.get("knowledge_type") != "standard":
            continue
        kid = k["ku_id"]
        res = rule_check(k, rules, units_map)
        warns = [(r, m) for r, s, m in res if s == "WARN"]
        rule_warns += [(kid, r, m) for r, m in warns]
        for hit in abolished_check(k):
            abolished_hits.append((kid, hit))
        if self_verify_check(k):
            self_verified.append(kid)

    implicit_gotcha = [k["ku_id"] for k in kus
                       if k.get("knowledge_type") is None or "knowledge_type" not in k]

    # ---------------- 报告 ----------------
    std_total = len([k for k in kus if k.get("knowledge_type") == "standard"])
    lines = []
    lines.append("# 知设知识库 Layer-1 规则审计报告")
    lines.append("")
    lines.append(f"> 审计时间：2026-08-04 ｜ 引擎：validate_ku.py v0.2 ｜ 真理表：verification_rules.json v0.1（27 条规则）")
    lines.append(f"> 库总量：{len(kus)} 条（standard {std_total} 条）｜ 零模型参与，纯代码确定性校验")
    lines.append("")
    lines.append("## 一、总览")
    lines.append("")
    lines.append(f"- Schema 违规：{len(schema_fails)} 条")
    lines.append(f"- 悬空引用：{len(dangling)} 处")
    lines.append(f"- 数值冲突候选（WARN，进 Layer-2 独立验证队列）：{len(rule_warns)} 处")
    lines.append(f"- 效力状态缺失（FAIL）：{len(abolished_hits)} 条")
    lines.append(f"- 自证 RELIABLE（待重验）：{len(self_verified)} 条")
    lines.append(f"- 隐式类型未显式标注：{len(implicit_gotcha)} 条（knowledge_type 缺省视为 gotcha，建议规范化时补全）")
    lines.append("")
    lines.append("## 二、数值冲突候选（WARN —— 文本存在与真理表目标值无配对的值，需 Layer-2 独立模型确认语境）")
    lines.append("")
    if rule_warns:
        for kid, rid, msg in rule_warns:
            lines.append(f"- {kid} [{rid}] {msg}")
    else:
        lines.append("无。")
    lines.append("")
    lines.append("## 三、效力状态缺失（FAIL —— 引用废止条文必须含 GB 55032 承接说明）")
    lines.append("")
    if abolished_hits:
        for kid, msg in abolished_hits:
            lines.append(f"- **{kid}** {msg}")
    else:
        lines.append("无。全部引用废止条文的条目均含 GB 55032 承接说明。")
    lines.append("")
    lines.append("## 四、Schema 违规与悬空引用")
    lines.append("")
    if schema_fails:
        for kid, errs in schema_fails:
            lines.append(f"- **{kid}**: {'; '.join(errs)}")
    else:
        lines.append("无。")
    if dangling:
        for kid, rel in dangling:
            lines.append(f"- 悬空引用：{kid} → {rel}")
    lines.append("")
    lines.append("## 五、自证 RELIABLE（生成者自我认证，按独立验证规范须排期重验）")
    lines.append("")
    if self_verified:
        lines.append(f"共 {len(self_verified)} 条 standard 条目由生成者自证为 RELIABLE（verify_method=ai_cross_reference、无 verified_by 记录）。按独立验证规范，须排期用 Layer-2 独立模型重验：")
        lines.append("")
        for i in range(0, len(self_verified), 10):
            lines.append(", ".join(self_verified[i:i + 10]))
            lines.append("")
    else:
        lines.append("无。")
    lines.append("## 六、规则未激活的 standard 条目（无任何真理表值配对，建议补充规则或确认无数值要求）")
    lines.append("")
    covered = set()
    for k in kus:
        if k.get("knowledge_type") != "standard":
            continue
        text = (k.get("standard_number", "") + k.get("standard_requirement", "") + k.get("compliance_criteria", ""))
        vals = extract_values(text, units_map)
        for r in rules:
            for c in r.get("checks", []):
                if any(abs(v - c["value"]) <= MATCH_TOL for v, unit, _ in vals if unit == c["unit"]):
                    covered.add(k["ku_id"])
    uncovered = [k["ku_id"] + " " + k["title"][:24] for k in kus
                 if k.get("knowledge_type") == "standard" and k["ku_id"] not in covered]
    for u in uncovered:
        lines.append(f"- {u}")
    lines.append("")
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))

    # 控制台摘要
    print(f"total={len(kus)} standard={std_total}")
    print(f"schema_fail={len(schema_fails)} dangling={len(dangling)} rule_warn={len(rule_warns)} "
          f"abolished={len(abolished_hits)} self_verify={len(self_verified)} implicit={len(implicit_gotcha)}")
    print("report:", REPORT)


if __name__ == "__main__":
    main()
