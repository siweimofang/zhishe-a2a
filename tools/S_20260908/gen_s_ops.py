# -*- coding: utf-8 -*-
# S批判定线gen: probe3定谳verdicts -> s_fixlist.json (KB kb_apply.py消费格式)
# 口径: 库内真实文本(探针ctx的【十】是视觉标记, 库内是裸'十'); op窗从库实取+field内count==1
# 改动位: 十→+(482+1) / 十→干(30+21) / 十→一(k12456) / 二→=(k20276b) = 536位
import json, sys, hashlib
from collections import defaultdict
sys.stdout.reconfigure(errors='replace')

KB     = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a\data\knowledge.json"
PROBE3 = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\_s_probe3.txt"
OUT    = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\s_fixlist.json"
REPORT = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\_s_gen_report.txt"

with open(KB, 'rb') as f:
    raw = f.read()
data = json.loads(raw.decode('utf-8'))
idx = {e['id']: e for e in data}

# ---------- 1. 解析probe3 ----------
dry21, rest668, sec = [], [], None
for line in open(PROBE3, encoding='utf-8'):
    line = line.rstrip('\n')
    if line.startswith('[2]'): sec = 2; continue
    if line.startswith('[3]'): sec = 3; continue
    if line.startswith('[账平]') or line.startswith('[0]') or line.startswith('[1'):
        sec = None; continue
    b = line.strip()
    if sec in (2, 3) and b.startswith('k'):
        head = b.split(' @')[0]
        eid, field = head.split('.')
        pos = int(b.split('@')[1].split(':')[0])
        if sec == 2:
            if eid == 'k20276':  # k20276a走特殊逻辑
                continue
            dry21.append((eid, field, pos))
        else:
            rest668.append((eid, field, pos))

rep = []
rep.append(f"[解析] dry21={len(dry21)} rest668={len(rest668)}")
assert len(dry21) == 21, f"dry21解析数{len(dry21)}!=21"
assert len(rest668) == 668, f"rest668解析数{len(rest668)}!=668"

# ---------- 2. verdicts (判定线人工终谳 0908) ----------
LEGAL_P = set(("""
k258.answer@195 k570.answer@141 k581.answer@154 k582.answer@117 k594.answer@154 k597.answer@168
k599.answer@223 k600.answer@188 k619.answer@211 k620.answer@254 k1743.answer@383 k1760.answer@210
k1797.question@18 k1797.answer@139 k4763.answer@471 k4766.answer@375 k4769.answer@5 k5018.answer@74
k5108.answer@924 k5110.answer@550 k5242.answer@8018 k5245.answer@1074 k6249.answer@72 k7509.answer@30
k8229.answer@135 k8281.question@6 k8456.answer@363 k9001.answer@304 k9058.answer@55 k9203.answer@10
k9206.answer@91 k9466.answer@44 k9763.question@3 k11951.question@4 k12467.answer@147 k12840.answer@38
k13412.answer@155 k14929.answer@521 k14943.answer@466 k15200.answer@507 k15201.answer@88 k15202.answer@201
k15208.answer@553 k16680.answer@465 k16991.answer@251 k17045.answer@381 k17046.answer@109 k17047.answer@92
k17049.answer@246 k17050.answer@67 k17051.answer@379 k17052.answer@410 k17412.answer@702 k17454.answer@353
k17457.answer@281 k17459.answer@243 k17836.answer@708 k17981.answer@287 k18585.answer@237 k19058.answer@500
k19058.answer@561 k19067.answer@795 k19082.answer@46 k19082.answer@87 k19084.answer@168 k19090.answer@225
k19091.answer@29 k19335.answer@535 k19633.answer@621 k19633.answer@624 k19656.answer@116 k19843.answer@125
k19844.answer@155 k19889.answer@402 k20294.answer@310 k20482.answer@751 k20483.answer@521 k20490.question@3
k20506.answer@258 k20678.answer@290 k21542.question@4 k21784.answer@74 k21898.answer@36 k22153.question@2
k22287.answer@464 k22473.answer@495 k22582.answer@21 k22651.answer@105 k22670.answer@35 k23060.answer@629
k23460.answer@597 k23571.answer@420 k23584.answer@433 k24068.answer@47 k24384.question@20 k25590.answer@375
k25822.answer@75 k26084.question@0 k26201.answer@285 k26298.question@9 k26428.answer@165 k26428.answer@352
k26547.answer@218 k27918.answer@341 k28283.question@0 k28967.question@10
""").split())

PEND_P = set(("""
k5088.answer@71 k5862.answer@359 k5997.answer@599 k6409.answer@518 k9521.answer@94 k10102.answer@208
k10716.answer@8 k10729.answer@412 k11205.answer@403 k12521.answer@705 k12739.answer@90 k12756.answer@185
k12762.answer@0 k12764.answer@45 k12765.answer@496 k14034.answer@257 k14909.answer@172 k16190.answer@198
k16250.answer@119 k16529.answer@741 k16587.answer@347 k16694.answer@68 k16745.answer@72 k16931.answer@154
k16940.answer@306 k17026.answer@22 k17376.answer@631 k17870.answer@206 k18118.answer@266 k18125.answer@107
k18220.answer@785 k18245.answer@127 k18257.answer@524 k18257.answer@680 k18601.answer@726 k18625.answer@201
k18736.answer@5 k19061.answer@733 k19468.answer@255 k20240.answer@541 k20537.answer@49 k20549.answer@40
k20562.answer@767 k22153.answer@34 k25244.answer@627 k25795.answer@81 k25834.answer@70 k25851.question@0
k25883.answer@0 k26250.answer@609
""").split())

DRY668_P = set(("""
k4255.answer@291 k4255.answer@373 k4262.answer@149 k4262.answer@184 k4263.answer@290 k4267.answer@279
k4280.answer@158 k4280.answer@225 k4280.answer@257 k4281.answer@190 k4289.answer@287 k4296.answer@380
k4299.answer@277 k4299.answer@356 k4407.answer@352 k12507.answer@148 k12507.answer@401 k13336.answer@257
k14405.answer@190 k14416.answer@188 k14928.answer@771 k17437.answer@114 k18383.answer@342 k18383.answer@374
k19103.answer@729 k20565.answer@797 k21743.answer@117 k23244.answer@408 k23454.answer@733 k23503.answer@486
""").split())

# 覆盖完备性: verdicts与668清单精确互证
keys668 = {f"{a}.{b}@{c}" for a, b, c in rest668}
allv = LEGAL_P | PEND_P | DRY668_P
lost = allv - keys668          # verdicts里写了但668没有 => 冗余(可能记错id/pos)
dup  = LEGAL_P & PEND_P | LEGAL_P & DRY668_P | PEND_P & DRY668_P
assert not lost, f"verdicts冗余(668无此位): {sorted(lost)}"
assert not dup, f"verdicts跨类重复: {sorted(dup)}"
uncovered = keys668 - allv     # 未覆盖位 => 默认FIX_PLUS, 数量必须=482
assert len(uncovered) == 482, f"默认FIX_PLUS数{len(uncovered)}!=482"
assert len(LEGAL_P) == 106 and len(PEND_P) == 50 and len(DRY668_P) == 668 - 106 - 50 - len(uncovered) and len(DRY668_P) == 30

fix_plus  = [(a, b, c, '+') for a, b, c in rest668 if f"{a}.{b}@{c}" not in allv]
fix_dry   = [(a, b, c, '干') for a, b, c in rest668 if f"{a}.{b}@{c}" in DRY668_P]
fix_dry  += [(a, b, c, '干') for a, b, c in dry21]
legal_cnt = sum(1 for a, b, c in rest668 if f"{a}.{b}@{c}" in LEGAL_P)
pend_cnt  = sum(1 for a, b, c in rest668 if f"{a}.{b}@{c}" in PEND_P)
rep.append(f"[分类] FIX_PLUS={len(fix_plus)} FIX_DRY={len(fix_dry)}(668内30+dry21) LEGAL={legal_cnt} PEND={pend_cnt}")

# ---------- 3. 同(id,field)跨ch检查(仅k20276允许) ----------
fch = defaultdict(set)
for eid, field, pos, ch in fix_plus + fix_dry:
    fch[(eid, field)].add(ch)
bad = [k for k, v in fch.items() if len(v) > 1 and k != ('k20276', 'question')]
assert not bad, f"同field跨ch: {bad}"

# ---------- 4. 逐位验证+分组窗op ----------
groups = defaultdict(list)
for eid, field, pos, ch in fix_plus + fix_dry:
    groups[(eid, field, ch)].append(pos)

ops, meta, fail = [], [], []
for (eid, field, ch), poss in sorted(groups.items()):
    t = (idx[eid].get(field) or '')
    poss = sorted(set(poss))
    badpos = [p for p in poss if p >= len(t) or t[p] != '十']
    if badpos:
        fail.append(f"{eid}.{field}@{badpos} 现场字符异常"); continue
    lo, hi = poss[0], poss[-1]
    W = 14
    win = None
    while W <= 90:
        s, e2 = max(0, lo - W), min(len(t), hi + W + 1)
        cand = t[s:e2]
        if t.count(cand) == 1:
            win = (s, e2, cand); break
        W += 8
    if win is None:
        fail.append(f"窗唯一性失败 {eid}.{field} @{lo}-{hi}"); continue
    s, e2, old = win
    fixset = {p - s for p in poss}   # 窗内相对位(修复: poss是全文位, 须减窗起点s)
    new = ''.join(ch if i in fixset else c for i, c in enumerate(old))
    if new == old:
        fail.append(f"new==old {eid}.{field} @{lo}-{hi}"); continue
    ops.append({'id': eid, 'field': field, 'old': old, 'new': new})
    meta.append(f"op {eid}.{field} pos{lo}-{hi} n={len(poss)} ch={ch} win={len(old)}c")

# ---------- 5. 特殊op: k20276(十→+ 与 二→=, 窗互斥) / k12456(十→一) ----------
e = idx['k20276']; t = e.get('question') or ''
pa = [p for p in range(len(t)) if t[p] == '十' and t[max(0, p - 2):p] == '费用']
pb = [p for p in range(len(t)) if t[p] == '二' and p > 0 and t[p - 1] == '）' and t[p + 1:p + 2] == '总']
rep.append(f"[k20276] 十病灶位={pa} 二病灶位={pb} q={t!r}")
assert len(pa) == 1 and len(pb) == 1, f"k20276定位异常 pa={pa} pb={pb}"
# opA: 费用十( -> 费用+(
s, e2, W = pa[0], pa[0] + 1, 6
while t.count(t[max(0, s - W):e2 + W]) != 1: W += 4
oldA = t[max(0, s - W):e2 + W]
assert '）二总造价' not in oldA, "opA窗撞二位"
ra = pa[0] - max(0, s - W)
assert oldA[ra] == '十'
ops.append({'id': 'k20276', 'field': 'question', 'old': oldA, 'new': oldA[:ra] + '+' + oldA[ra + 1:]})
# opB: )二总 -> )=总
s, e2, W = pb[0], pb[0] + 1, 6
while t.count(t[max(0, s - W):e2 + W]) != 1: W += 4
oldB = t[max(0, s - W):e2 + W]
assert '十' not in oldB, "opB窗撞十位"
rb = pb[0] - max(0, s - W)
assert oldB[rb] == '二'
ops.append({'id': 'k20276', 'field': 'question', 'old': oldB, 'new': oldB[:rb] + '=' + oldB[rb + 1:]})
meta.append(f"op k20276.question A={oldA!r} B={oldB!r}")

e = idx['k12456']; t = e.get('answer') or ''
pc = [p for p in range(len(t)) if t[p] == '十' and t[p + 1:p + 3] == '一槽']
rep.append(f"[k12456] 一槽病灶位={pc} ctx={[t[max(0,p-12):p+14] for p in pc]!r}")
assert len(pc) == 1, f"k12456定位异常 {pc}"
s, e2, W = pc[0], pc[0] + 1, 8
while t.count(t[max(0, s - W):e2 + W]) != 1: W += 4
oldC = t[max(0, s - W):e2 + W]
rc = pc[0] - max(0, s - W)
assert oldC[rc] == '十'
ops.append({'id': 'k12456', 'field': 'answer', 'old': oldC, 'new': oldC[:rc] + '一' + oldC[rc + 1:]})
meta.append(f"op k12456.answer {oldC!r} -> 一字槽")

# ---------- 6. op终检: field内old count==1 (对齐kb_apply门禁) ----------
for i, op in enumerate(ops):
    c = (idx[op['id']].get(op['field']) or '').count(op['old'])
    if c != 1:
        fail.append(f"op{i} {op['id']}.{op['field']} old count={c}!=1")
assert not fail, "gen失败:\n" + "\n".join(fail)

# ---------- 7. 汇总+账平 ----------
n_plus  = sum(op['old'].count('十') - op['new'].count('十') for op in ops)          # 十净减
n_dry   = sum(op['old'].count('十') - op['new'].count('干') if False else 0 for op in ops)
changed = sum(1 for a, b in zip([o['old'] for o in ops], [o['new'] for o in ops]) if a != b)
diff_plus = sum(a.count('十') - b.count('十') for a, b in zip([o['old'] for o in ops], [o['new'] for o in ops]))
# 逐op字符映射账
cnt_map = defaultdict(int)
for op in ops:
    for a, b in zip(op['old'], op['new']):
        if a != b:
            cnt_map[(a, b)] += 1
rep.append("[字符映射账] " + json.dumps({f"{a}->{b}": n for (a, b), n in sorted(cnt_map.items())}, ensure_ascii=False))
rep.append(f"[ops] 总op数={len(ops)} 改动位总数={sum(cnt_map.values())}")

fixobj = {
    "batch": "S1",
    "expect": f"十total 3146 -> {3146 - sum(n for (a, b), n in cnt_map.items() if a == '十')}; ops={len(ops)}; 映射账={dict((f'{a}{b}', n) for (a, b), n in sorted(cnt_map.items()))}",
    "fixlist": ops,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(fixobj, f, ensure_ascii=False, indent=1)
with open(REPORT, 'w', encoding='utf-8') as f:
    f.write("\n".join(rep + ["", "[meta]"] + meta))
print(f"GEN GREEN ops={len(ops)} map={dict(cnt_map)} -> {OUT}")
