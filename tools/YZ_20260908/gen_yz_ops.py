# -*- coding: utf-8 -*-
# YZ批判定线gen: 允→充族(充许→允许)全形态65位 -> yz_fixlist.json (kb_apply.py消费格式)
# 依据: GZ3交底留账[2] "不充许(允→充族)余33位 需族批定谳(J1式流程)"; 判定线probe1/2/3扩围=A类32位
# 自包含: 直接从盘上knowledge.json现态逐位重定位(不依赖probe文件), 防批间漂移
# 窗规则: 同(id,field)先并一窗扩唯一; 唯一化失败或窗吞他位→子簇分裂; 窗禁含他簇替换位
import json, io, sys, hashlib
from collections import defaultdict
sys.stdout.reconfigure(errors='replace')

KB     = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a\data\knowledge.json"
OUT    = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\yz_fixlist.json"
REPORT = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\_yz_gen_report.txt"

with open(KB, 'rb') as f:
    raw = f.read()
assert len(raw) == 39247547, f"pre字节{len(raw)}!=39247547"
text = raw.decode('utf-8')
assert not text.startswith('\ufeff') and text.count('\n') == text.count('\r\n')
data = json.loads(text)
assert len(data) == 29788
assert json.dumps(data, ensure_ascii=False, indent=1).replace('\n', '\r\n') == text
idx = {e['id']: e for e in data}

def s_cnt(ch):
    return sum((e.get(f) or '').count(ch) for e in data for f in ('question', 'answer'))

def norm_map(t):
    idx_map, norm = [], []
    for ti, ch in enumerate(t):
        if ch in ('\r', '\n'):
            continue
        idx_map.append(ti)
        norm.append(ch)
    return ''.join(norm), idx_map

# ---------- 1. pre census ----------
rep = []
def log(s):
    rep.append(s); print(s, flush=True)

log(f"[pre] bytes={len(raw)} sha1={hashlib.sha1(raw).hexdigest()[:8]} 条目={len(data)}")
pre_cx, pre_bc = s_cnt('充许'), s_cnt('不充许')
pre_yx, pre_by = s_cnt('允许'), s_cnt('不允许')
pre_chong, pre_shi, pre_jg, pre_dg = s_cnt('充'), s_cnt('十'), s_cnt('竣工'), s_cnt('倒干')
log(f"[pre] 充许={pre_cx} 不充许={pre_bc} 允许={pre_yx} 不允许={pre_by} 充={pre_chong} 十={pre_shi} 竣工={pre_jg} 倒干={pre_dg}")
assert pre_shi == 2611 and pre_jg == 1015 and pre_dg == 12, "S批post锚漂移"

# 范围闭合检查: 其他允X伤形态 ('未充'14位已逐位定谳=合法: 未充分/未充满/尚未充分, _yz_weichong.txt)
extra = {w: s_cnt(w) for w in ('充准', '充诺', '充从', '充服', '所充')}
log(f"[范围闭合] 其他允X伤候选: {extra} (未充=14已定谳合法)")
assert all(v == 0 for v in extra.values()), "发现充许族外新形态, 停手扩围"

# ---------- 2. 逐位重定位 (norm拼接跨行覆盖) ----------
positions = []   # (id, field, ti, tag)
for e in data:
    for fld in ('question', 'answer'):
        t = e.get(fld) or ''
        if '充' not in t and '许' not in t:
            continue
        norm, imap = norm_map(t)
        i = 0
        while True:
            s = norm.find('充许', i)
            if s < 0:
                break
            i = s + 1
            tag = 'B' if (s >= 1 and norm[s-1] == '不') else 'A'
            positions.append((e['id'], fld, imap[s], tag))
assert len(positions) == 65, f"逐位重定位{len(positions)}!=65"
b_cnt = sum(1 for p in positions if p[3] == 'B')
log(f"[定位] 总位={len(positions)} B类(不充许)={b_cnt} A类(充许)={len(positions)-b_cnt}")
assert b_cnt == 33
# 连写vs劈词自洽: s_cnt('充许') = 65 - 劈词位(充后紧跟换行)
split_cnt = 0
for eid, fld, ti, tag in positions:
    t = (idx[eid].get(fld) or '')
    if ti + 1 < len(t) and t[ti + 1] in ('\r', '\n'):
        split_cnt += 1
log(f"[形态] 劈词位(充⏎许)={split_cnt} 连写充许={pre_cx} 自洽={pre_cx == 65 - split_cnt}")
assert pre_cx == 65 - split_cnt and pre_bc == 33 and pre_yx == 2386 and pre_by == 624, "充许族pre账不符"

# ---------- 3. 分簇+造窗 ----------
groups = defaultdict(list)
for eid, fld, ti, tag in positions:
    groups[(eid, fld)].append((ti, tag))

ops, meta, fail = [], [], []
GAP = 45
for (eid, fld) in sorted(groups):
    t = (idx[eid].get(fld) or '')
    pts = sorted(p for p, _ in groups[(eid, fld)])
    tags = {p: tg for p, tg in groups[(eid, fld)]}
    # 分簇: 相邻位距>GAP则分裂
    clusters, cur = [], [pts[0]]
    for p in pts[1:]:
        if p - cur[-1] <= GAP:
            cur.append(p)
        else:
            clusters.append(cur); cur = [p]
    clusters.append(cur)
    for cl in clusters:
        lo, hi = cl[0], cl[-1]
        span = hi - lo + 1
        W = max(14, span // 2 + 8)
        win = None
        while W <= 200:
            s0, e0 = max(0, lo - W), min(len(t), hi + W + 1)
            cand = t[s0:e0]
            # 条件1: field内唯一; 条件2: 窗内充许位恰好=本簇位(禁吞他簇替换位)
            n_cx_in_win = sum(1 for p in pts if s0 <= p < e0)
            if t.count(cand) == 1 and n_cx_in_win == len(cl):
                win = (s0, e0, cand); break
            W += 8
        if win is None:
            fail.append(f"窗唯一化失败 {eid}.{fld} @{lo}-{hi}"); continue
        s0, e0, old = win
        fixset = {p - s0 for p in cl}
        assert all(old[i] == '充' for i in fixset), f"窗内非充位 {eid}.{fld}"
        new = ''.join('允' if i in fixset else c for i, c in enumerate(old))
        assert new != old
        ops.append({'id': eid, 'field': fld, 'old': old, 'new': new})
        meta.append(f"op {eid}.{fld} pos{lo}-{hi} n={len(cl)} 类={'B' if tags[lo]=='B' else 'A'} win={len(old)}c")

# ---------- 4. op终检: field内old count==1 (kb_apply门禁) + 窗互斥(同field不重叠) ----------
byfield = defaultdict(list)
for op in ops:
    byfield[(op['id'], op['field'])].append(op)
for (eid, fld), oplist in byfield.items():
    t = (idx[eid].get(fld) or '')
    spans = []
    for op in oplist:
        c = t.count(op['old'])
        if c != 1:
            fail.append(f"{eid}.{fld} old count={c}!=1")
        s0 = t.find(op['old'])
        spans.append((s0, s0 + len(op['old']) - 1))
    spans.sort()
    for (a1, a2), (b1, b2) in zip(spans, spans[1:]):
        if a2 >= b1:
            fail.append(f"{eid}.{fld} 窗重叠 {a1}-{a2} vs {b1}-{b2}")
assert not fail, "gen失败:\n" + "\n".join(fail)

# ---------- 5. 仿真(post账+字节账) ----------
simdata = json.loads(text)
simm = {e['id']: e for e in simdata}
for op in ops:
    t = simm[op['id']][op['field']]
    assert t.count(op['old']) == 1
    simm[op['id']][op['field']] = t.replace(op['old'], op['new'])

def s_cnt2(ch):
    return sum((e.get(f) or '').count(ch) for e in simdata for f in ('question', 'answer'))

def norm_cnt(pat):
    n = 0
    for e in simdata:
        for f in ('question', 'answer'):
            nm, _ = norm_map(e.get(f) or '')
            i = 0
            while True:
                i = nm.find(pat, i)
                if i < 0: break
                n += 1; i += 1
    return n

post = {
    '充许(norm)': norm_cnt('充许'), '不充许(norm)': norm_cnt('不充许'),
    '允许': s_cnt2('允许'), '不允许': s_cnt2('不允许'), '充': s_cnt2('充'),
    '十': s_cnt2('十'), '竣工': s_cnt2('竣工'), '倒干': s_cnt2('倒干'),
}
log(f"[post仿真] {post}")
assert post['充许(norm)'] == 0 and post['不充许(norm)'] == 0, "post仿真仍有充许残"
assert post['允许'] == 2451 and post['不允许'] == 657 and post['充'] == 3801
assert post['十'] == 2611 and post['竣工'] == 1015 and post['倒干'] == 12

dump = json.dumps(simdata, ensure_ascii=False, indent=1).replace('\n', '\r\n')
delta = len(dump.encode('utf-8')) - len(raw)
log(f"[字节账] sim_dump={len(dump.encode('utf-8'))} pre={len(raw)} delta={delta} (逐op等长应=0)")
assert delta == 0

cnt_map = defaultdict(int)
for op in ops:
    for a, b in zip(op['old'], op['new']):
        if a != b:
            cnt_map[(a, b)] += 1
log("[字符映射账] " + json.dumps({f"{a}->{b}": n for (a, b), n in sorted(cnt_map.items())}, ensure_ascii=False))
assert cnt_map == {('充', '允'): 65}

fixobj = {
    "batch": "YZ",
    "expect": "充许(norm) 65 -> 0; 充许连写63+劈词2全清; 允许2386->2451; 不允许624->657; 充3866->3801; bytes=39247547(delta=0); ops=65; 映射账={充允:65}",
    "fixlist": ops,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(fixobj, f, ensure_ascii=False, indent=1)
with open(REPORT, 'w', encoding='utf-8') as f:
    f.write("\n".join(rep + ["", "[meta]"] + meta))
print(f"YZ_GEN_GREEN ops={len(ops)} touched={len(byfield)} -> {OUT}")
