# -*- coding: utf-8 -*-
"""
Gotchas库结构完整性一键检查
检查项：Schema合规 / 交叉引用 / 分片同步 / 索引新鲜度
"""
import json, os, sys, re, io
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a\gotchas"
DATA_DIR = os.path.join(BASE, "data", "v1.0")
ALL_KU = os.path.join(DATA_DIR, "all_ku.json")
SCHEMA_FILE = os.path.join(BASE, "schema", "ku_schema_v1.json")
INDEX_PKL = os.path.join(BASE, "retriever", "hybrid_index.pkl")

# 合法枚举值
VALID_STAGES = {f"STAGE_0{i}" for i in range(1, 9)}
VALID_SEVERITIES = {"SEV_CRITICAL", "SEV_HIGH", "SEV_MEDIUM", "SEV_LOW"}
VALID_ROLES = {"ROLE_OWNER", "ROLE_DESIGNER", "ROLE_CONTRACTOR", "ROLE_INDUSTRY"}
VALID_PROBLEM_TYPES = {"TYPE_FRAUD", "TYPE_QUALITY", "TYPE_OMISSION", "TYPE_DELAY", "TYPE_COST", "TYPE_COMMUNICATION"}
VALID_TRADES = {"TRADE_DESIGN", "TRADE_DEMOLISH", "TRADE_PLUMBING", "TRADE_WATERPROOF",
                "TRADE_TILE", "TRADE_CARPENTRY", "TRADE_PAINT", "TRADE_CABINET",
                "TRADE_DOOR", "TRADE_FLOOR", "TRADE_BATHROOM", "TRADE_ELECTRICAL"}
VALID_MATERIALS = {"MAT_PIPE", "MAT_WIRE", "MAT_CEMENT", "MAT_TILE", "MAT_PAINT",
                   "MAT_BOARD", "MAT_GLUE", "MAT_HARDWARE", "MAT_APPLIANCE", "MAT_FURNITURE"}
ID_PATTERN = re.compile(r"^GZ-SY-\d{4,6}$")

errors = []
warnings = []

print("=" * 60)
print("Gotchas库结构完整性检查")
print("=" * 60)

# 加载数据
with open(ALL_KU, "r", encoding="utf-8") as f:
    data = json.load(f)
print(f"\n[load] {len(data)} KUs")

# === 检查1: Schema合规 ===
print("\n--- 检查1: Schema合规 ---")
all_ids = set()
schema_errors = 0

for i, ku in enumerate(data):
    kid = ku.get("ku_id", f"<missing>@index{i}")
    
    # ku_id格式
    if not ID_PATTERN.match(kid):
        errors.append(f"[SCHEMA] {kid}: ku_id格式不合法")
        schema_errors += 1
    if kid in all_ids:
        errors.append(f"[SCHEMA] {kid}: ku_id重复")
        schema_errors += 1
    all_ids.add(kid)
    
    # 必填字段
    for field in ["title", "stage", "severity", "description", "how_to_avoid"]:
        if not ku.get(field):
            errors.append(f"[SCHEMA] {kid}: 缺少必填字段 '{field}'")
            schema_errors += 1
    
    # 枚举值
    if ku.get("stage") and ku["stage"] not in VALID_STAGES:
        errors.append(f"[SCHEMA] {kid}: stage='{ku['stage']}' 不合法")
        schema_errors += 1
    if ku.get("severity") and ku["severity"] not in VALID_SEVERITIES:
        errors.append(f"[SCHEMA] {kid}: severity='{ku['severity']}' 不合法")
        schema_errors += 1
    for r in ku.get("role", []):
        if r not in VALID_ROLES:
            errors.append(f"[SCHEMA] {kid}: role含非法值 '{r}'")
            schema_errors += 1
    for t in ku.get("trade", []):
        if t not in VALID_TRADES:
            errors.append(f"[SCHEMA] {kid}: trade含非法值 '{t}'")
            schema_errors += 1
    for m in ku.get("material", []):
        if m not in VALID_MATERIALS:
            errors.append(f"[SCHEMA] {kid}: material含非法值 '{m}'")
            schema_errors += 1
    for pt in ku.get("problem_type", []):
        if pt not in VALID_PROBLEM_TYPES:
            errors.append(f"[SCHEMA] {kid}: problem_type含非法值 '{pt}'")
            schema_errors += 1
    
    # 长度限制
    title = ku.get("title", "")
    if len(title) > 80:
        warnings.append(f"[SCHEMA] {kid}: title超长({len(title)}/80)")
    desc = ku.get("description", "")
    if desc and len(desc) < 50:
        warnings.append(f"[SCHEMA] {kid}: description过短({len(desc)}/50)")
    if desc and len(desc) > 500:
        warnings.append(f"[SCHEMA] {kid}: description超长({len(desc)}/500)")

print(f"  错误: {schema_errors}  警告: {len(warnings)}")
if schema_errors == 0:
    print("  ✓ 全部合规")

# === 检查2: 交叉引用完整性 ===
print("\n--- 检查2: 交叉引用完整性 ---")
dangling = 0
for ku in data:
    kid = ku.get("ku_id", "")
    for ref in ku.get("related_ku_ids", []):
        if ref not in all_ids:
            errors.append(f"[REF] {kid}: 引用了不存在的 '{ref}'")
            dangling += 1

print(f"  悬空引用: {dangling}")
if dangling == 0:
    print("  ✓ 全部引用有效")

# === 检查3: 分片同步 ===
print("\n--- 检查3: 分片同步 ---")
split_issues = 0

# by_severity
sev_dir = os.path.join(DATA_DIR, "by_severity")
if os.path.isdir(sev_dir):
    from collections import defaultdict
    sev_count = defaultdict(int)
    for ku in data:
        sev_count[ku.get("severity", "").lower()] += 1
    
    for sev, expected_count in sev_count.items():
        fpath = os.path.join(sev_dir, f"{sev}.json")
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                actual = len(json.load(f))
            if actual != expected_count:
                errors.append(f"[SPLIT] {sev}.json: 期望{expected_count}条, 实际{actual}条")
                split_issues += 1
        else:
            errors.append(f"[SPLIT] 缺少文件 {sev}.json")
            split_issues += 1
else:
    errors.append("[SPLIT] by_severity目录不存在")
    split_issues += 1

print(f"  分片问题: {split_issues}")
if split_issues == 0:
    print("  ✓ 分片与主文件一致")

# === 检查4: 索引新鲜度 ===
print("\n--- 检查4: 索引新鲜度 ---")
if os.path.exists(INDEX_PKL):
    json_mtime = os.path.getmtime(ALL_KU)
    pkl_mtime = os.path.getmtime(INDEX_PKL)
    json_time = datetime.fromtimestamp(json_mtime)
    pkl_time = datetime.fromtimestamp(pkl_mtime)
    
    if pkl_mtime >= json_mtime:
        print(f"  ✓ 索引({pkl_time:%m-%d %H:%M}) ≥ 数据({json_time:%m-%d %H:%M})")
    else:
        errors.append(f"[INDEX] 索引过期! 数据更新:{json_time:%m-%d %H:%M}, 索引构建:{pkl_time:%m-%d %H:%M}")
        print(f"  ✗ 索引过期! 需重建")
else:
    errors.append("[INDEX] hybrid_index.pkl不存在")
    print("  ✗ 索引文件不存在")

# === 汇总 ===
print("\n" + "=" * 60)
print(f"检查完成: {len(errors)} 错误, {len(warnings)} 警告")
print("=" * 60)

if errors:
    print("\n[错误清单]")
    for e in errors[:20]:
        print(f"  {e}")
    if len(errors) > 20:
        print(f"  ... 还有 {len(errors)-20} 条")

if warnings:
    print(f"\n[警告清单] (前10条)")
    for w in warnings[:10]:
        print(f"  {w}")
    if len(warnings) > 10:
        print(f"  ... 还有 {len(warnings)-10} 条")

sys.exit(1 if errors else 0)
