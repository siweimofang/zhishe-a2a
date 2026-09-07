# -*- coding: utf-8 -*-
"""RN14 锚定解析模块 v3: 9片判定单 lesions → 现态KB位点解析.
阶梯: L1精确(窗口内全出现位) → L2 maili修复 → L3剥行 → L4省略号 → L5注记兜底 → L6模糊对齐
指派: 全解枚举(置换集不变性接受) + maili覆盖终态证据. 供gen复用. 零写库零提交."""
import json, io, os, re, sys, difflib
from collections import defaultdict, Counter

WS = r'C:\Users\Administrator\.qoderworkcn\workspace\msklrypny7w2454t'
REPO = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a'
KB_PATH = os.path.join(REPO, 'data', 'knowledge.json')
MAI_PATH = r'D:\projects\非默认outputs\修复微批_埋理族421op_fixlist_20260907.json'

NOTE_TAIL = re.compile(r'\s*[（(]第[一二三四五六七八九十百0-9]+处[）)]\s*$')
EXP_LESIONS = {1: 10, 2: 73, 3: 179, 4: 129, 5: 276, 6: 208, 7: 214, 8: 195, 9: 170}
FUZZ_RATIO = 0.85
SOL_CAP = 20000


def load_kb():
    raw = open(KB_PATH, 'rb').read()
    text = raw.decode('utf-8')
    assert not text.startswith('\ufeff'), 'BOM!'
    assert text.count('\n') == text.count('\r\n'), '盘上存在裸LF'
    entries = json.loads(text)
    assert len(entries) == 29788, 'entries drift %d' % len(entries)
    return raw, text, entries


def load_mai():
    mai = json.load(io.open(MAI_PATH, encoding='utf-8'))
    m = defaultdict(list)
    for o in mai['fixlist']:
        m[(o['id'], o['field'])].append((o['old'], o['new']))
    return m, mai


def find_all(hay, needle):
    if not needle:
        return []
    out = []
    i = hay.find(needle)
    while i >= 0:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def is_meta_note(sc):
    if not sc:
        return False
    return len(sc) <= 20 and ('同字段' in sc or '第二处' in sc or '第三处' in sc)


def clean_ctx(ctx):
    c = ctx.replace('⏎', '\n')
    while True:
        c2 = NOTE_TAIL.sub('', c)
        if c2 == c:
            break
        c = c2
    return c


def parse_records():
    recs = []
    for sn in range(1, 10):
        v = json.load(io.open(os.path.join(WS, 'rn14_verdicts_shard%02d.json' % sn), encoding='utf-8'))
        if sn == 1:
            vl = v['verdicts_lesion']
            assert len(vl) == EXP_LESIONS[1], 's1 lesions %d' % len(vl)
            for gid, r in sorted(vl.items()):
                if r['kind'] == 'double_lir_mg':
                    cands = [('理人', '埋入')]
                else:
                    assert r['kind'] == 'single_rk', r['kind']
                    tok = r['fix'].split('(', 1)[1].rsplit(')', 1)[0]
                    cands = [(tok.replace('入', '人', 1), tok)]
                recs.append(dict(shard=1, gid=gid, id=r['id'], fld=r['fld'], ctx=r['ctx'],
                                 cands=cands, src=r['fix'], kind=r['kind']))
        else:
            assert len(v['lesions']) == EXP_LESIONS[sn], 's%d lesions %d' % (sn, len(v['lesions']))
            for r in v['lesions']:
                if sn <= 5:
                    w = r['word']
                    cs = []
                    for i, ch in enumerate(w):
                        if ch == '人':
                            cs.append((w, w[:i] + '入' + w[i + 1:]))
                        elif ch == '入':
                            cs.append((w[:i] + '人' + w[i + 1:], w))
                    seen = set()
                    cands = []
                    for a, b in cs:
                        if a != b and (a, b) not in seen:
                            seen.add((a, b))
                            cands.append((a, b))
                    recs.append(dict(shard=sn, gid=r['gid'], id=r['id'], fld=r['fld'], ctx=r['ctx'],
                                     cands=cands, src=w, kind='word'))
                elif sn <= 8:
                    a, b = r['fix'].split('→')
                    assert len(a) == len(b), r['fix']
                    kid, fld = r['key'].split(':', 1)
                    recs.append(dict(shard=sn, gid=r['gid'], id=kid, fld=fld, ctx=r['ctx'],
                                     cands=[(a, b)], src=r['fix'], kind='fix'))
                else:
                    a, b = r['op'].split('→')
                    assert len(a) == len(b), r['op']
                    kid, fld = r['key'].split(':', 1)
                    recs.append(dict(shard=sn, gid=r['gid'], id=kid, fld=fld, ctx=r['ctx'],
                                     cands=[(a, b)], src=r['op'], kind='op'))
    assert len(recs) == 1454, 'total lesions %d' % len(recs)
    return recs


def maili_repair_ctx(c_n, pairs):
    rep = c_n
    for mo, mn in pairs:
        if len(mo) == len(mn):
            rep = rep.replace(mo, mn)
    return rep


def maili_cover(old, new, pairs):
    for mo, mn in pairs:
        if len(mo) != len(mn):
            continue
        for i in find_all(mo, old):
            if mn[i:i + len(old)] == new:
                return True
    return False


def _split_in_window(w, p, old, mode):
    sw = w.replace('\n', '')
    sq = sw.find(old)
    if sq < 0:
        return None
    m = [i for i, ch in enumerate(w) if ch != '\n']
    if sq >= len(m):
        return None
    return (mode, p + m[sq])


def _sub_set(old, new, p):
    return frozenset((p + i, b) for i, (a, b) in enumerate(zip(old, new)) if a != b)


def record_sites(r, body, sbody, sidx, mai_pairs, fuzzy=True):
    """单记录定位: 返回 [(old,new,[(mode,pos)...])] 仅含非空sites候选"""
    c_n = clean_ctx(r['ctx'])
    sc = c_n.replace('\n', '')
    results = []
    for (old, new) in r['cands']:
        raw_sites = []

        def scan_window(p, anchor_len, mode):
            w = body[p:p + anchor_len]
            for q in find_all(w, old):
                if q + len(old) <= len(w):
                    raw_sites.append((mode, p + q))
            if not any(body[p + q:p + q + len(old)] == old for q in find_all(w, old)
                       if q + len(old) <= len(w)):
                hit = _split_in_window(w, p, old, mode + '_split')
                if hit:
                    raw_sites.append(hit)

        # L1 精确整ctx (窗口内全出现位)
        for p in find_all(body, c_n):
            scan_window(p, len(c_n), 'exact')
        # L2 maili窗口修复后精确
        if mai_pairs:
            rep = maili_repair_ctx(c_n, mai_pairs)
            if rep != c_n:
                for p in find_all(body, rep):
                    scan_window(p, len(rep), 'repaired')
        # L3 剥行整ctx (跨行劈词主通道)
        if sc and old in sc:
            so = sc.find(old)
            for sp in find_all(sbody, sc):
                raw_sites.append(('stripped', sidx[sp + so]))
        # L4 省略号ctx
        if '...' in c_n or '…' in c_n:
            parts = [x.replace('\n', '') for x in re.split(r'\.\.\.|…', c_n)]
            head, tail = parts[0], parts[-1]
            so_h = head.find(old) if head else -1
            so_t = tail.find(old) if tail else -1
            hs = find_all(sbody, head) if head else []
            ts = find_all(sbody, tail) if tail else []
            if not head:
                for t in ts:
                    if so_t >= 0:
                        raw_sites.append(('ellipsis', sidx[t + so_t]))
            elif not tail:
                for h in hs:
                    if so_h >= 0:
                        raw_sites.append(('ellipsis', sidx[h + so_h]))
            else:
                for h in hs:
                    if so_h >= 0:
                        raw_sites.append(('ellipsis', sidx[h + so_h]))
                    for t in ts:
                        if h < t and (t - (h + len(head))) <= 300 and so_t >= 0:
                            raw_sites.append(('ellipsis', sidx[t + so_t]))
        # L5 注记ctx兜底
        if is_meta_note(sc):
            occ = find_all(sbody, old)
            if 0 < len(occ) <= 20:
                for o in occ:
                    raw_sites.append(('note', sidx[o]))
        seen = set()
        dd = []
        for mode, p in raw_sites:
            if p not in seen:
                seen.add(p)
                dd.append((mode, p))
        if dd:
            results.append((old, new, dd))
            continue
        # L6 模糊对齐: old各出现位周边窗口与ctx相似度
        if fuzzy and sc and old in sc:
            so = sc.find(old)
            cands = []
            for sp in find_all(sbody, old)[:20]:
                st0 = max(0, sp - so)
                win = sbody[st0:st0 + len(sc)]
                if not win:
                    continue
                ratio = difflib.SequenceMatcher(None, sc, win).ratio()
                if ratio >= FUZZ_RATIO:
                    cands.append((ratio, sidx[sp]))
            cands.sort(key=lambda x: -x[0])
            for ratio, p in cands[:10]:
                raw_sites.append(('fuzzy', p))
            seen = set()
            dd = []
            for mode, p in raw_sites:
                if p not in seen:
                    seen.add(p)
                    dd.append((mode, p))
            if dd:
                results.append((old, new, dd))
    return results


def resolve(recs, idx, mai_map):
    cache = {}

    def field_state(kid, fld):
        key = (kid, fld)
        if key not in cache:
            body = idx[kid].get(fld) or ''
            sidx = [i for i, ch in enumerate(body) if ch != '\n']
            sbody = body.replace('\n', '')
            cache[key] = (body, sbody, sidx)
        return cache[key]

    groups = defaultdict(list)
    for r in recs:
        r['status'] = None
        if r['id'] not in idx:
            r['status'] = 'SURFACE'
            r['why'] = 'missing_entry'
            continue
        body, sbody, sidx = field_state(r['id'], r['fld'])
        pairs = mai_map.get((r['id'], r['fld']), [])
        r['sites_opts'] = record_sites(r, body, sbody, sidx, pairs)
        if not r['sites_opts']:
            ev = None
            if len(r['cands']) == 1:
                old, new = r['cands'][0]
                if body.count(old) == 0 and maili_cover(old, new, pairs):
                    ev = (old, new)
            if ev:
                r['status'] = 'BLOCKED'
                r['blocked'] = ev
            else:
                r['status'] = 'SURFACE'
                r['why'] = 'no_sites'
            continue
        groups[(r['id'], r['fld'])].append(r)

    for key, gr in groups.items():
        body, sbody, sidx = cache[key]
        opts = []
        for r in gr:
            o = []
            for old, new, modes in r['sites_opts']:
                for mode, p in modes:
                    o.append((old, new, p, _sub_set(old, new, p), mode))
            opts.append(o)
        # 快路径: 全单选且互不冲突
        if all(len(o) == 1 for o in opts):
            subs = [o[0][3] for o in opts]
            if len(frozenset().union(*subs)) == sum(len(s) for s in subs):
                for r, o in zip(gr, opts):
                    old, new, p, ss, mode = o[0]
                    r['status'] = 'EXEC'
                    r['old'], r['new'], r['pos'], r['mode'] = old, new, p, mode
                continue
        sols = []
        used = []

        def bt(k):
            if len(sols) >= SOL_CAP:
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
            sets = set(sol[0][3] for sol in sols)
            union = frozenset().union(*[o[3] for sol in sols for o in sol])
            invariant = all(frozenset().union(*[o[3] for o in sol]) == union for sol in sols)
            if invariant and len(sols) < SOL_CAP:
                for r, opt in zip(gr, sols[0]):
                    old, new, p, ss, mode = opt
                    r['status'] = 'EXEC'
                    r['old'], r['new'], r['pos'], r['mode'] = old, new, p, mode
                gr[0]['bijection'] = len(sols)
                continue
        for r in gr:
            r['status'] = 'SURFACE'
            r['why'] = 'assign_ambiguous' if sols else 'assign_fail'
    return recs


def diffs_of(old, new):
    return [(i, a, b) for i, (a, b) in enumerate(zip(old, new)) if a != b]


def EXEC_LIST(recs):
    return [r for r in recs if r['status'] == 'EXEC']


if __name__ == '__main__':
    sys.stdout.reconfigure(errors='replace')
    raw, text, entries = load_kb()
    idx = {e['id']: e for e in entries}
    mai_map, mai = load_mai()
    recs = parse_records()
    recs = resolve(recs, idx, mai_map)

    out = []

    def P(s):
        out.append(str(s))

    st = Counter((r['status'], r.get('mode', r.get('why', ''))) for r in recs)
    P('== 状态分布 ==')
    for k, c in sorted(st.items(), key=lambda x: str(x[0])):
        P('  %s: %d' % (k, c))
    by_shard = defaultdict(Counter)
    for r in recs:
        by_shard[r['shard']][r['status']] += 1
    P('== 分片状态 ==')
    for sn in sorted(by_shard):
        P('  s%d: %s' % (sn, dict(by_shard[sn])))

    P('== BLOCKED 明细 ==')
    for r in recs:
        if r['status'] == 'BLOCKED':
            P('  s%d %s %s.%s %s→%s ctx=%r' %
              (r['shard'], r['gid'], r['id'], r['fld'], r['blocked'][0], r['blocked'][1],
               clean_ctx(r['ctx'])[:30]))

    P('== 双射接受组(同置换集多解) ==')
    seen_bij = set()
    for r in recs:
        if r.get('bijection'):
            key = (r['id'], r['fld'])
            if key not in seen_bij:
                seen_bij.add(key)
                grp = [x for x in recs if x['status'] == 'EXEC' and (x['id'], x['fld']) == key]
                P('  %s.%s n_rec=%d n_sol=%s: %s' %
                  (key[0], key[1], len(grp), r['bijection'],
                   '; '.join('%s@%d' % (x['old'][:6], x['pos']) for x in sorted(grp, key=lambda x: x['pos']))))

    P('== SURFACE 明细 ==')
    for r in recs:
        if r['status'] == 'SURFACE':
            body = idx[r['id']].get(r['fld']) or ''
            P('  s%d %s %s.%s cands=%s why=%s ctx=%r' %
              (r['shard'], r['gid'], r['id'], r['fld'],
               [(a[:8], b[:8]) for a, b in r['cands']], r.get('why'),
               clean_ctx(r['ctx'])[:44]))
            for old, new in r['cands']:
                occs = find_all(body, old)
                P('      old=%r 场内出现n=%d %s' % (old[:8], len(occs),
                  ['@%d ...%s...' % (i, body[max(0, i - 8):i + len(old) + 8]) for i in occs[:3]]))

    P('== EXEC mode 分布 ==')
    P('  %s' % dict(Counter(r['mode'] for r in EXEC_LIST(recs))))
    P('== fuzzy EXEC 明细 ==')
    for r in EXEC_LIST(recs):
        if r['mode'] == 'fuzzy':
            body = idx[r['id']][r['fld']]
            P('  s%d %s %s.%s %s→%s @%d ctx=%r 场景=%r' %
              (r['shard'], r['gid'], r['id'], r['fld'], r['old'][:8], r['new'][:8], r['pos'],
               clean_ctx(r['ctx'])[:30], body[max(0, r['pos'] - 12):r['pos'] + len(r['old']) + 12]))

    P('== token出现位vs记录数 罩门检查(occ==n_rec) ==')
    tok_rec = defaultdict(set)
    for r in EXEC_LIST(recs):
        tok_rec[(r['id'], r['fld'], r['old'])].add(r['pos'])
    for (kid, fld, old), ps in sorted(tok_rec.items()):
        body = idx[kid][fld]
        occ = len(find_all(body, old))
        if occ == len(ps):
            P('  %s.%s %r: occ=%d == exec位=%d (该field此token全翻,需目验无合法态)' % (kid, fld, old[:8], occ, len(ps)))

    P('== 焦点抽查 ==')
    for kid, fld, tok in [('k15098', 'answer', '充人'), ('k15098', 'answer', '充人情性'),
                          ('k4350', 'answer', '卡人'), ('k18043', 'answer', '理人'),
                          ('k10520', 'answer', '清理人库'), ('k16318', 'answer', '喷人')]:
        body = idx[kid][fld]
        ps = find_all(body, tok)
        P('  %s.%s %r count=%d pos=%s' % (kid, fld, tok, len(ps), ps[:6]))
    for r in recs:
        if r['id'] in ('k15098', 'k13005'):
            P('  %s记录: s%d %s %s status=%s pos=%s mode=%s cands=%s ctx=%r' %
              (r['id'], r['shard'], r['gid'], r['kind'], r['status'], r.get('pos'), r.get('mode'),
               [(a[:10], b[:10]) for a, b in r['cands']], clean_ctx(r['ctx'])[:36]))

    io.open(os.path.join(WS, 'rn14_resolve_report.txt'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('RESOLVE_DONE exec=%d blocked=%d surface=%d' % (
        sum(1 for r in recs if r['status'] == 'EXEC'),
        sum(1 for r in recs if r['status'] == 'BLOCKED'),
        sum(1 for r in recs if r['status'] == 'SURFACE')))
