# -*- coding: utf-8 -*-
# RN14 人→入族 全量执行件生成器 (gen段)
# 输入: 9片判定单(lesions=1454) + 埋理批fixlist(ctx修复/终态覆盖证据) + 眼筛基准shard TXT
# 口径: 逐gid逐ctx锚定禁replace-all; skip_special不执行; uncertain/backlog不入库(蒸馏禁区)
# 阶梯: L1精确(窗口内全出现位)→L2maili修复→L3剥行→L4省略号→L5注记→L6唯一出现位→L7模糊
#       + 跨记录位点指派(置换集不变性) + 手术定谳3条(硬断言) + 跨片重复申报1条跳过
# 门禁: byte-identity+HEAD blob → 指派穷尽 → 聚类唯一窗口 → 顺序仿真 → token双口径
#       → 回归/spots → fixlist双路落盘(wal + outputs字节全等)
import json, io, os, re, sys, hashlib, shutil, subprocess
from bisect import bisect_left
from collections import defaultdict, Counter
sys.stdout.reconfigure(errors='replace')
sys.path.insert(0, r'C:\Users\Administrator\.qoderworkcn\workspace\msklrypny7w2454t')
import rn14_resolve as R

WS = R.WS
REPO = R.REPO
OUT_DIR = r'D:\projects\非默认outputs'
FIX_WS = os.path.join(WS, 'rn_patch14_fixlist.json')
REP = os.path.join(WS, 'rn14_gen_report.txt')
LOG = []


def log(s):
    LOG.append(str(s))


WL = {('人', '入'), ('理', '埋'), ('情', '惰')}

# ---- 0. 装载 + byte-identity + HEAD blob 门 ----
raw, text, entries = R.load_kb()
idx = {e['id']: e for e in entries}
mai_map, mai = R.load_mai()
dump_pre = json.dumps(entries, ensure_ascii=False, indent=1)
assert '\r' not in dump_pre
assert dump_pre.replace('\n', '\r\n') == text, 'byte-identity precondition FAILED'
blob = subprocess.run(['git', '-C', REPO, 'show', 'HEAD:data/knowledge.json'],
                      capture_output=True, check=True).stdout
btext = blob.decode('utf-8')
assert '\r' not in btext
assert btext.replace('\n', '\r\n') == text, 'HEAD blob → CRLF != 盘'
HEAD = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD'], capture_output=True,
                      check=True).stdout.decode().strip()
BLOBSHA = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD:data/knowledge.json'],
                         capture_output=True, check=True).stdout.decode().strip()
st = subprocess.run(['git', '-C', REPO, 'status', '--porcelain'], capture_output=True,
                    check=True).stdout.decode()
assert 'knowledge.json' not in st, 'knowledge.json 有未提交改动'
sha1 = hashlib.sha1(raw).hexdigest()
sha256 = hashlib.sha256(raw).hexdigest()
log('0 pre门 OK entries=29788 bytes=%d HEAD=%s blob=%s sha1=%s' % (len(raw), HEAD[:9], BLOBSHA[:8], sha1[:10]))

# ---- 1. 解析 + 指派 ----
recs = R.parse_records()
recs = R.resolve(recs, idx, mai_map)
cnt = Counter(r['status'] for r in recs)
log('1 resolve: %s' % dict(cnt))

cache = {}

def field_state(kid, fld):
    key = (kid, fld)
    if key not in cache:
        body = idx[kid].get(fld) or ''
        sidx = [i for i, ch in enumerate(body) if ch != '\n']
        sbody = body.replace('\n', '')
        cache[key] = (body, sbody, sidx)
    return cache[key]

def assign_subset(gr):
    """对同组记录做位点指派(穷举, 置换集不变性接受), 就地写status"""
    body, sbody, sidx = field_state(gr[0]['id'], gr[0]['fld'])
    opts = []
    for r in gr:
        o = []
        for old, new, modes in r['sites_opts']:
            for mode, p in modes:
                o.append((old, new, p, R._sub_set(old, new, p), mode))
        opts.append(o)
    sols = []
    used = []

    def bt(k):
        if len(sols) >= R.SOL_CAP:
            return
        if k == len(gr):
            sols.append(list(used))
            return
        for opt in opts[k]:
            if any(used[j][3] & opt[3] for j in range(len(used))):
                continue
            used.append(opt)
            bt(k + 1)
            used.pop()

    bt(0)
    if sols:
        union = frozenset().union(*[o[3] for sol in sols for o in sol])
        if len(sols) < R.SOL_CAP and all(frozenset().union(*[o[3] for o in sol]) == union for sol in sols):
            for r, opt in zip(gr, sols[0]):
                old, new, p, ss, mode = opt
                r['status'] = 'EXEC'
                r['old'], r['new'], r['pos'], r['mode'] = old, new, p, mode
            return True
    return False

# ---- 2. 手术段 ----
# 2a. assign_fail组内同位重复申报拆分 → 保留首位EXEC, 余SKIP_DUP, 组内重指派
dup_pairs = []
for _ in range(5):
    changed = False
    keys = set((r['id'], r['fld']) for r in recs
               if r['status'] == 'SURFACE' and r.get('why') == 'assign_fail')
    for key in keys:
        grp = [r for r in recs if (r['id'], r['fld']) == key and r['status'] == 'SURFACE']
        bysig = defaultdict(list)
        for r in grp:
            if len(r['sites_opts']) == 1 and len(r['sites_opts'][0][2]) == 1:
                old, new, modes = r['sites_opts'][0]
                bysig[(old, new, modes[0][1])].append(r)
        for sig, rs in bysig.items():
            if len(rs) > 1:
                rs = sorted(rs, key=lambda x: (x['shard'], x['gid']))
                keep = rs[0]
                old, new, modes = keep['sites_opts'][0]
                keep['status'] = 'EXEC'
                keep['old'], keep['new'], keep['pos'], keep['mode'] = old, new, modes[0][1], modes[0][0]
                for d in rs[1:]:
                    d['status'] = 'SKIP_DUP'
                    d['dup_of'] = 's%d %s' % (keep['shard'], keep['gid'])
                dup_pairs.append((keep['shard'], keep['gid'], keep['id'], keep['fld'],
                                  old, [ (d['shard'], d['gid']) for d in rs[1:] ]))
                changed = True
        rest = [r for r in grp if r['status'] == 'SURFACE']
        if rest and len(rest) < len(grp):
            if assign_subset(rest):
                changed = True
    if not changed:
        break
log('2a dup拆分: %s' % dup_pairs)

# 2b. 唯一出现位兜底 (raw n==1, 或 raw0+stripped n==1)
for r in recs:
    if r['status'] != 'SURFACE' or len(r['cands']) != 1:
        continue
    body, sbody, sidx = field_state(r['id'], r['fld'])
    sc = R.clean_ctx(r['ctx']).replace('\n', '')
    old, new = r['cands'][0]
    if old not in sc:
        continue
    occ = R.find_all(body, old)
    if len(occ) == 1:
        r['status'] = 'EXEC'
        r['old'], r['new'], r['pos'], r['mode'] = old, new, occ[0], 'uniq'
    elif len(occ) == 0:
        socc = R.find_all(sbody, old)
        if len(socc) == 1:
            r['status'] = 'EXEC'
            r['old'], r['new'], r['pos'], r['mode'] = old, new, sidx[socc[0]], 'uniq_stripped'

# 2c. 手术定谳3条 (census/shard TXT证据, 硬断言)
bygid = {(r['shard'], r['gid']): r for r in recs}

def surgical(shard, gid, frag, off, old, new, mode, note):
    r = bygid[(shard, gid)]
    assert r['status'] == 'SURFACE', 'surgical %s not surface: %s' % (gid, r['status'])
    body = idx[r['id']][r['fld']]
    fs = R.find_all(body, frag)
    assert len(fs) == 1, 'surgical frag not unique %s: %d' % (gid, len(fs))
    pos = fs[0] + off
    assert body[pos:pos + len(old)] == old, 'surgical old mismatch %s' % gid
    r['status'] = 'EXEC'
    r['old'], r['new'], r['pos'], r['mode'] = old, new, pos, mode
    r['note'] = note
    log('2c surgical s%d %s %s.%s %s→%s @%d' % (shard, gid, r['id'], r['fld'], old, new, pos))

surgical(2, '000713', '管道总人口和', 2, '总人口', '总入口', 'manual_frag',
         '判定单word=管道入口与场文总人口差前缀字; census组B|口(shard02:000713); 换字同语义人→入, 按场文定锚')
surgical(3, '000929', '插人同轴电缆', 0, '插人', '插入', 'manual_census',
         'census行(shard03:000929)原文=正确形插入接线孔内+病灶插人同轴电缆; 判定单ctx首段误转写插入→插人')
surgical(6, '002799', '然后将木槽板压人木台豁口', 6, '压人', '压入', 'manual_census',
         'census窗口偏移16定谳第一处压人(压人木台豁口下面); 同ctx第二处压人部分@567与@652 census未录病灶, 眼筛基准不动')

cnt = Counter(r['status'] for r in recs)
log('2 surgical后: %s' % dict(cnt))
assert cnt.get('SURFACE', 0) == 0, '仍有SURFACE: %s' % [
    (r['shard'], r['gid'], r['id'], r.get('why')) for r in recs if r['status'] == 'SURFACE']
assert cnt.get('EXEC', 0) == 1444 and cnt.get('BLOCKED', 0) == 9 and cnt.get('SKIP_DUP', 0) == 1, \
    '分类账不平: %s' % dict(cnt)

# ---- 3. 位点图 + 白名单 ----
posmap = defaultdict(dict)
rec_pos = defaultdict(list)
pair_cnt = Counter()
for r in recs:
    if r['status'] != 'EXEC':
        continue
    old, new, p = r['old'], r['new'], r['pos']
    diffs = R.diffs_of(old, new)
    assert diffs, 'no diff %s' % r['gid']
    body = idx[r['id']][r['fld']]
    # 位点映射: r['pos']=old首字符raw位(所有模式统一约定); old内偏移d经sidx映射到raw
    # (exact/repaired/manual为连续old两者等价; exact_split/stripped/ellipsis/note/fuzzy/
    #  uniq_stripped的old跨\n, 必须走sidx, 直接p+d会错位——000672实证)
    sidx = [i for i, ch in enumerate(body) if ch != '\n']
    sp0 = bisect_left(sidx, p)
    assert sp0 < len(sidx) and sidx[sp0] == p and body[p] == old[0], \
        'pos映射失败 %s@%d' % (r['gid'], p)
    for d, a, b in diffs:
        cp = sidx[sp0 + d]
        assert body[cp] == a, 'char mismatch %s@%d' % (r['gid'], cp)
        prev = posmap[(r['id'], r['fld'])].get(cp)
        assert prev is None or prev == b, '位点冲突 %s@%d' % (r['id'], cp)
        posmap[(r['id'], r['fld'])][cp] = b
        rec_pos[(r['id'], r['fld'])].append((r['shard'], r['gid'], cp))
        pair_cnt[(a, b)] += 1
assert dict(pair_cnt) == {('人', '入'): 1444, ('理', '埋'): 1, ('情', '惰'): 1}, dict(pair_cnt)
log('3 位点=%d 对账 %s' % (sum(len(v) for v in posmap.values()), dict(pair_cnt)))

# ---- 4. 聚类 (rn13机器: 最小唯一窗口 + 跨簇合并) ----
def grow(body, p, n):
    lo, hi = p, p + 1
    last = 0
    while True:
        w = body[lo:hi]
        if body.count(w) == 1:
            break
        cand = []
        if lo > 0:
            cand.append((body.count(body[lo - 1:hi]), 0, lo - 1, hi))
        if hi < n:
            cand.append((body.count(body[lo:hi + 1]), 1, lo, hi + 1))
        assert cand, 'growth exhausted'
        cand.sort(key=lambda x: (x[0], x[1] != last))
        _, d, lo, hi = cand[0]
        last = d
    return lo, hi

clusters = {}
multi = 0
for (kid, fld), pm in sorted(posmap.items()):
    body = idx[kid][fld]
    n = len(body)
    allpos = set(pm.keys())
    cls = []
    assigned = set()
    for p in sorted(allpos):
        if p in assigned:
            continue
        lo, hi = grow(body, p, n)
        mine = {q for q in allpos if lo <= q < hi}
        assert not ((set(range(lo, hi)) - mine) & allpos), 'foreign lesion %s:%s' % (kid, fld)
        cls.append({'pos': set(mine), 'lo': lo, 'hi': hi})
        assigned |= mine
    changed = True
    while changed:
        changed = False
        for i in range(len(cls)):
            for j in range(i + 1, len(cls)):
                A, B = cls[i], cls[j]
                if A is None or B is None:
                    continue
                ha = any(A['lo'] <= q < A['hi'] for q in B['pos'])
                hb = any(B['lo'] <= q < B['hi'] for q in A['pos'])
                # 相邻并簇(执行令补丁k18043: 双字位理人→埋入须单op一步到位;
                # 并簇唯一性由包含唯一子窗保证; k15098充人情性同理并入)
                adj = (A['hi'] == B['lo']) or (B['hi'] == A['lo'])
                if ha or hb or adj:
                    A['pos'] |= B['pos']
                    A['lo'] = min(A['lo'], B['lo'])
                    A['hi'] = max(A['hi'], B['hi'])
                    cls[j] = None
                    changed = True
        cls = [c for c in cls if c is not None]
    cov = set()
    for c in cls:
        cov |= c['pos']
        if len(c['pos']) > 1:
            multi += 1
    assert cov == allpos, 'coverage drift %s:%s' % (kid, fld)
    clusters[(kid, fld)] = cls
log('4 聚类: fields=%d multi-pos簇=%d' % (len(clusters), multi))

# ---- 5. ops构建 + 顺序仿真 + 门禁 ----
ops = []
for (kid, fld), cls in sorted(clusters.items()):
    body = idx[kid][fld]
    pm = posmap[(kid, fld)]
    for c in sorted(cls, key=lambda c: -c['lo']):
        lo, hi, pset = c['lo'], c['hi'], c['pos']
        old = body[lo:hi]
        new = ''.join(pm.get(lo + i, ch) for i, ch in enumerate(old))
        assert old != new and len(old) == len(new)
        assert all(d in WL for d in zip(old, new) if d[0] != d[1])
        for i in range(lo, hi):
            if i not in pset:
                assert new[i - lo] == body[i]
        assert body.count(old) == 1, 'anchor not unique %s:%s' % (kid, fld)
        assert hi - lo <= 1500
        assert '\x00' not in old
        ops.append({'id': kid, 'field': fld, 'old': old, 'new': new})
points = sum(1 for o in ops for a, b in zip(o['old'], o['new']) if a != b)
ids_touched = len(set(o['id'] for o in ops))
assert points == 1446, 'points drift %d' % points
log('5 ops=%d fields=%d entries=%d points=1446' % (len(ops), len(ops_by_field := ops) and len(set((o['id'], o['field']) for o in ops)), ids_touched))

ops_by_field = defaultdict(list)
for o in ops:
    ops_by_field[(o['id'], o['field'])].append(o)
sim = {}
for key in sorted(ops_by_field):
    cur = idx[key[0]][key[1]]
    for o in ops_by_field[key]:
        assert cur.count(o['old']) == 1, 'sim pre %s %r' % (key, o['old'][:20])
        cur = cur.replace(o['old'], o['new'], 1)
    for o in ops_by_field[key]:
        assert o['old'] not in cur, 'sim residue %s' % (key,)
    # 位点重derive门: sim必须逐字符==pre在posmap位点上的精确替换 (充要校验;
    # 原窗口delta算术门对跨界token失效——k10520最小窗'人库'而token'清理入库'
    # 跨边界, 算术pred=0实际+1, 弃算术门)
    pm = posmap[key]
    exp = list(idx[key[0]][key[1]])
    for cp in sorted(pm, reverse=True):
        exp[cp] = pm[cp]
    assert ''.join(exp) == cur, 'positional re-derive %s' % (key,)
    sim[key] = cur
log('5b 顺序仿真+位点重derive OK (%d fields)' % len(sim))

# 回归门(全局): maili成果与合法词不动
# '人人'特例: 词首人→入的跨界合法消耗恰13处(深入人心×4/射入人眼×2/让人入眠/
# 浸入人的/侵入人体/工人入场×3), 逐处context审计见rn14_regr_debug.txt;
# 其余token严格不变
REGR = ['预理', '理件', '理设', '重理', '设计人员', '施工人员', '人员', '人们', '绊倒人', '人造石']
REGR_DELTA = {'人人': -13}
pre_all = Counter()
post_all = Counter()
for e in entries:
    for f in ('question', 'answer'):
        t = e.get(f) or ''
        for T in REGR + list(REGR_DELTA):
            pre_all[T] += t.count(T)
        key = (e['id'], f)
        t2 = sim.get(key, t)
        for T in REGR + list(REGR_DELTA):
            post_all[T] += t2.count(T)
if any(pre_all[T] != post_all[T] for T in REGR) or \
   any(post_all[T] != pre_all[T] + d for T, d in REGR_DELTA.items()):
    drift = {T: (pre_all[T], post_all[T]) for T in REGR + list(REGR_DELTA) if pre_all[T] != post_all[T]}
    dbg = ['REGR-DRIFT %s' % drift]
    for e in entries:
        for f in ('question', 'answer'):
            key = (e['id'], f)
            t = e.get(f) or ''
            t2 = sim.get(key, t)
            for T in drift:
                if t.count(T) != t2.count(T):
                    for r in recs:
                        if r['status'] == 'EXEC' and (r['id'], r['fld']) == key:
                            dbg.append('  %s %s T=%r pre=%d post=%d gid=%s old=%r new=%r pos=%s' % (
                                r['id'], f, T, t.count(T), t2.count(T), r['gid'], r['old'], r['new'], r['pos']))
                    i = 0
                    while True:
                        i = t.find(T, i)
                        if i < 0:
                            break
                        if t2[i:i + len(T)] != T:
                            dbg.append('    hit@%d pre=%r post=%r' % (i, t[max(0, i - 10):i + len(T) + 10], t2[max(0, i - 10):i + len(T) + 10]))
                        i += 1
    with io.open(os.path.join(WS, 'rn14_regr_debug.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(dbg))
assert all(pre_all[T] == post_all[T] for T in REGR), \
    '回归漂移(严格): %s' % {T: (pre_all[T], post_all[T]) for T in REGR if pre_all[T] != post_all[T]}
assert all(post_all[T] == pre_all[T] + d for T, d in REGR_DELTA.items()), \
    '回归漂移(delta): %s' % {T: (pre_all[T], post_all[T]) for T in REGR_DELTA if post_all[T] != pre_all[T] + REGR_DELTA[T]}
log('5d 回归门 OK %s' % dict(pre_all))

# spots(现态值来自pre探针, post期望按病灶语义)
SPOTS = [
    ('k18043', 'answer', '理人', 0), ('k18043', 'answer', '埋入', 1),
    ('k10520', 'answer', '清理人库', 0), ('k10520', 'answer', '清理入库', 1),
    ('k20196', 'answer', '沉人孔内', 0), ('k20196', 'answer', '沉入孔内', 1),
    ('k16318', 'answer', '喷人', 0), ('k16318', 'answer', '喷入', 2),
    ('k11798', 'answer', '细致人微', 0), ('k11798', 'answer', '细致入微', 1),
    ('k10647', 'answer', '锤人', 0), ('k10647', 'answer', '锤入', 1),
    ('k12558', 'answer', '灯泡旋人', 0), ('k12558', 'answer', '灯泡旋入', 1),
    ('k18816', 'answer', '理人', 0),
    ('k11222', 'answer', '无从入', 1),
    ('k18317', 'answer', '总人口', 0), ('k18317', 'answer', '总入口', 1),
    ('k12559', 'answer', '压人木台豁口', 0), ('k12559', 'answer', '压入木台豁口', 1),
    ('k12559', 'answer', '压人部分', 2),
    ('k4185', 'answer', '插人同轴电缆', 0), ('k4185', 'answer', '插入同轴电缆', 2),  # pre已有1处正确形((2)节), 修复后=2 (probe实锤)
    ('k16483', 'answer', '装人', 0), ('k16483', 'answer', '放人', 0),
    ('k15098', 'answer', '充人情性', 0), ('k15098', 'answer', '充入惰性', 1),
    ('k12576', 'answer', '插人', 0),
]
for kid, fld, tok, exp in SPOTS:
    v = sim[(kid, fld)].count(tok)
    assert v == exp, 'spot %s.%s %r: %d != %d' % (kid, fld, tok, v, exp)
log('5e spots OK (%d)' % len(SPOTS))

# ---- 6. TXT合法同现罩门检查(报告性) ----
txt_re = re.compile(r'^(\d{6}) (\S+) (k\d+:(?:question|answer)) \|(.*)\|?\s*$')
txt_rec = {}
lesion_gids = set()
for sn in range(1, 10):
    v = json.load(io.open(os.path.join(WS, 'rn14_verdicts_shard%02d.json' % sn), encoding='utf-8'))
    if sn == 1:
        lesion_gids |= set(('1', g) for g in v['verdicts_lesion'])
    else:
        lesion_gids |= set((str(sn), x['gid']) for x in v['lesions'])
for sn in range(1, 10):
    p = os.path.join(WS, 'rn14_shard_%02d.txt' % sn)
    if not os.path.exists(p):
        continue
    for ln in io.open(p, encoding='utf-8'):
        m = txt_re.match(ln.rstrip('\n'))
        if m:
            txt_rec[(str(sn), m.group(1))] = (m.group(3).split(':')[0], m.group(3).split(':')[1], m.group(4))
flags = []
tok_occ = defaultdict(set)
for r in recs:
    if r['status'] == 'EXEC':
        tok_occ[(r['id'], r['fld'], r['old'])].add(r['pos'])
for (kid, fld, old), ps in sorted(tok_occ.items()):
    body = idx[kid][fld]
    if len(R.find_all(body, old)) != len(ps):
        continue
    for (sn, gid), (tid, tfld, tctx) in txt_rec.items():
        if tid == kid and tfld == fld and (sn, gid) not in lesion_gids and old in tctx:
            flags.append('%s.%s %r occ==位 但TXT s%s:%s(非病灶)ctx含该token' % (kid, fld, old[:8], sn, gid))
log('6 TXT合法同现flags=%d %s' % (len(flags), flags[:10]))

# ---- 7. fixlist双路落盘 + ledger + pre快照 ----
meta = {
    'batch': 'RN14 人→入族全量 修复微批 (9片判定单合并执行)',
    'gen': 'gen_rn14_fixlist.py; 解析器rn14_resolve.py v3(L1精确窗口内全出现位/L2maili修复/L3剥行/L4省略号/L5注记/L6唯一位/L7模糊 + 位点指派置换集不变性); 埋理批421op fixlist做ctx修复与终态覆盖证据',
    'craft': '逐gid逐ctx锚定禁replace-all(op=最小唯一窗口count==1); 手术定谳3条(000713总人口/000929插人同轴电缆/002799压人木台豁口,带硬断言与census证据); 跨片重复申报1条(s3:001240=s2:000517同位)跳过; 聚类最小唯一窗口rn13机器',
    'blocked': '终态拦截9: s1八双字位(k3963/k10716/k11657/k12097/k12358/k17249/k18816/k21665,埋理批已修埋入)+k13005(埋理批顺手人→入); maili窗口覆盖证据+old=0双证',
    'skip_note': '各片skip_special一律未执行(48跨片dup+4片内同位+11存疑+1 maili已修位由判定单承担); 11条uncertain与BACKLOG_NEW 6条不入库(蒸馏禁区)',
    'pre_state': 'HEAD=%s blob=%s entries=29788 bytes=%d sha1=%s' % (HEAD[:9], BLOBSHA[:8], len(raw), sha1[:10]),
    'families': '执行1444记录(ren 1445点人→入含双字位分量+理→埋1+情→惰1); mode %s' % dict(Counter(r['mode'] for r in recs if r['status'] == 'EXEC')),
}
expect = {'numstat': '以实态diff为准', 'entries': ids_touched, 'ops': len(ops),
          'points': 1446, 'exec_records': 1444, 'blocked_terminal': 9, 'skip_dup': 1,
          'lesion_records': 1454}
fix = {'meta': meta, 'expect': expect, 'fixlist': ops}
buf = json.dumps(fix, ensure_ascii=False, indent=1).replace('\n', '\r\n')
with io.open(FIX_WS, 'w', encoding='utf-8', newline='') as f:
    f.write(buf)
FIX_OUT = os.path.join(OUT_DIR, '修复微批_人入族%dop_fixlist_20260907.json' % len(ops))
shutil.copyfile(FIX_WS, FIX_OUT)
with io.open(FIX_WS, 'rb') as f:
    a = f.read()
with io.open(FIX_OUT, 'rb') as f:
    b = f.read()
assert a == b, 'fixlist双路不一致'
log('7 fixlist双路落盘字节全等 (%d B): %s' % (len(a), FIX_OUT))

ledger = []
for r in recs:
    ledger.append({'shard': r['shard'], 'gid': r['gid'], 'id': r['id'], 'fld': r['fld'],
                   'kind': r['kind'], 'src': r['src'],
                   'verdict_old': r['cands'][0][0], 'verdict_new': r['cands'][0][1],
                   'status': r['status'], 'mode': r.get('mode', ''),
                   'pos': r.get('pos'), 'old': r.get('old'), 'new': r.get('new'),
                   'note': r.get('note', ''), 'dup_of': r.get('dup_of', ''),
                   'blocked': list(r['blocked']) if r.get('blocked') else []})
LED_WS = os.path.join(WS, 'rn14_ledger.json')
with io.open(LED_WS, 'w', encoding='utf-8') as f:
    json.dump(ledger, f, ensure_ascii=False, indent=1)
LED_OUT = os.path.join(OUT_DIR, '人入族全量执行ledger_20260907.json')
shutil.copyfile(LED_WS, LED_OUT)

pre_state = {'head': HEAD, 'blob': BLOBSHA, 'sha1': sha1, 'sha256': sha256,
             'bytes': len(raw), 'entries': 29788,
             'spots_pre': {'k18043.理人': 1, 'k18816.理人': 0, 'k10520.清理人库': 1,
                           'k20196.沉人孔内': 1, 'k16318.喷人': 2, 'k11798.细致人微': 1,
                           'k10647.锤人': 1, 'k12558.灯泡旋人': 1, 'k15098.充人情性': 1},
             'notice': '判定线pre态定谳见_rn14_patch_notice.txt; 本快照为执行令pre基线'}
PS_WS = os.path.join(WS, 'rn14_pre_state.json')
with io.open(PS_WS, 'w', encoding='utf-8') as f:
    json.dump(pre_state, f, ensure_ascii=False, indent=1)
shutil.copyfile(PS_WS, os.path.join(OUT_DIR, '人入族pre_state快照_20260907.json'))

with io.open(REP, 'w', encoding='utf-8') as f:
    f.write('\n'.join(LOG) + '\nRN14_FIXLIST_GREEN\n')
print('RN14_FIXLIST_GREEN ops=%d entries=%d points=1446 exec=1444 blocked=9 dup=1' %
      (len(ops), ids_touched))
