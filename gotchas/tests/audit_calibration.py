# -*- coding: utf-8 -*-
"""
筛选高风险KU用于内容真实性校准
筛选条件：
1. evidence.source_type = "industry_standard" (教科书来源，最可能与实战脱节)
2. frequency含"高频" (影响面大)
3. 从未被人工校准过 (last_reviewed_at为空或created_by=ai且verified=false)
输出：待审清单，按severity降序
"""
import json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a\gotchas"
ALL_KU = os.path.join(BASE, "data", "v1.0", "all_ku.json")

with open(ALL_KU, "r", encoding="utf-8") as f:
    data = json.load(f)

# 筛选高风险条目
high_risk = []
for ku in data:
    evidence = ku.get("evidence", {})
    metadata = ku.get("metadata", {})
    source_type = evidence.get("source_type", "")
    frequency = evidence.get("frequency", "")
    created_by = metadata.get("created_by", "")
    last_reviewed = metadata.get("last_reviewed_at")
    
    # 条件1: 教科书/行业标准来源
    is_textbook = source_type in ("industry_standard", "national_standard")
    # 条件2: 高频
    is_high_freq = "高频" in frequency
    # 条件3: AI生成且未被人工审过（排除今天刚校准的）
    never_reviewed = (created_by == "ai" and not last_reviewed) or \
                     (last_reviewed is None and created_by != "human")
    
    # 至少满足2个条件
    score = int(is_textbook) + int(is_high_freq) + int(never_reviewed)
    if score >= 2:
        high_risk.append({
            "ku_id": ku.get("ku_id"),
            "title": ku.get("title", "")[:50],
            "severity": ku.get("severity", ""),
            "source_type": source_type,
            "frequency": frequency,
            "created_by": created_by,
            "last_reviewed": last_reviewed or "从未",
            "risk_score": score,
            "description_snippet": ku.get("description", "")[:80]
        })

# 按severity + risk_score排序
sev_order = {"SEV_CRITICAL": 4, "SEV_HIGH": 3, "SEV_MEDIUM": 2, "SEV_LOW": 1}
high_risk.sort(key=lambda x: (sev_order.get(x["severity"], 0), x["risk_score"]), reverse=True)

print(f"筛选结果: {len(high_risk)} 条高风险KU（共532条）")
print(f"筛选条件: 教科书来源/高频/未人工审 至少满足2项")
print("=" * 80)

for i, item in enumerate(high_risk[:30], 1):
    print(f"\n{i:2d}. [{item['ku_id']}] {item['title']}")
    print(f"    严重度: {item['severity']}  来源: {item['source_type']}  频率: {item['frequency']}")
    print(f"    创建: {item['created_by']}  最后审核: {item['last_reviewed']}  风险分: {item['risk_score']}/3")
    print(f"    摘要: {item['description_snippet']}...")

print(f"\n{'=' * 80}")
print(f"总计 {len(high_risk)} 条待审。建议每次审10条，每月一轮。")
