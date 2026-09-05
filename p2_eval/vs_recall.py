#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vs_recall.py - vs_vision 对拍召回评分器(批次六, 配合vs_vision.mjs的items落盘)
口径: 简化any-match(名归一化+双向子串, 允许一条目配多真值行)——与score_p2.py全量口径
     (关键词表+1:1分配)不完全一致; 同分器同真值下 structured vs text 头对头才是判定,
     0904基线82.1%(score_p2口径)仅作参考锚, 不做跨分器直比。
用法: python vs_recall.py <structured结果目录> <text结果目录>
"""
import csv, json, re, sys, os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def norm(s):
    s = (s or '').lower()
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', s)


def load_truth(path):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            base = re.sub(r'#r\d+$', '', (r.get('sample_id') or '')).strip()
            rows.append({'sample': base, 'entry': (r.get('truth_entry') or '').strip()})
    # 复跑行归并(同 benchmark_draft 156行→78组口径)
    dedup, seen = [], set()
    for r in rows:
        k = (r['sample'], norm(r['entry']))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    return dedup


def recall_for(dirpath, truth):
    sj = json.load(open(os.path.join(dirpath, 'summary.json'), encoding='utf-8'))
    out = {'dir': os.path.basename(dirpath), 'mode': sj.get('mode'), 'cells': {}}
    row_samples = sorted({r.get('sample') for r in sj.get('rows', [])})
    for prov in sj.get('providers', []):
        agg_m = agg_t = 0
        per = {}
        for sample in row_samples:
            rows = [r for r in sj.get('rows', [])
                    if r.get('provider') == prov and r.get('sample') == sample and r.get('ok')]
            t_rows = [r for r in truth
                      if sample == r['sample'] or sample.startswith(r['sample'] + '_')]
            if not rows or not t_rows:
                continue
            items = rows[0].get('items') or []
            names = [norm(x.get('name')) for x in items if norm(x.get('name'))]
            matched = 0
            for tr in t_rows:
                tn = norm(tr['entry'])
                if tn and any(tn in n or n in tn for n in names):
                    matched += 1
            per[sample] = {'matched': matched, 'truth': len(t_rows), 'items': len(items)}
            agg_m += matched
            agg_t += len(t_rows)
        out['cells'][prov] = {
            'per_sample': per,
            'recall': round(agg_m / agg_t, 4) if agg_t else None,
            'matched': agg_m, 'truth_total': agg_t,
        }
    return out


def main():
    s_dir, t_dir = sys.argv[1], sys.argv[2]
    here = os.path.dirname(os.path.abspath(__file__))
    truth = load_truth(os.path.join(here, 'truth_quote.csv'))
    samples = sorted({r['sample'] for r in truth})
    print(f'truth dedup rows: {len(truth)} | samples: {samples}')
    res = {'structured': recall_for(s_dir, truth), 'text': recall_for(t_dir, truth)}
    for kind, r in res.items():
        print(f"[{kind}] mode={r['mode']} dir={r['dir']}")
        for prov, c in r['cells'].items():
            per = ' '.join(f"{s}:{d['matched']}/{d['truth']}(条目{d['items']})"
                           for s, d in sorted(c['per_sample'].items()))
            rc = f"{c['recall']*100:.1f}%" if c['recall'] is not None else 'n/a'
            print(f"  {prov}: recall={rc} ({c['matched']}/{c['truth_total']}) | {per}")

    def best(r):
        vals = [c['recall'] for c in r['cells'].values() if c['recall'] is not None]
        return max(vals) if vals else 0.0
    bs, bt = best(res['structured']), best(res['text'])
    print(f"\nhead-to-head: structured_best={bs*100:.1f}% vs text_best={bt*100:.1f}%"
          f" | 基线参考82.1%(0904 score_p2口径, 非同分器仅作锚)")
    verdict = 'PASS' if bs >= bt else 'FAIL'
    print(f"VERDICT: {verdict} (判定=structured召回不低于text, 即切默认前提)")
    json.dump({'verdict': verdict, 'structured_best': bs, 'text_best': bt, **res},
              open(os.path.join(s_dir, 'vs_recall_summary.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('saved:', os.path.join(s_dir, 'vs_recall_summary.json'))


if __name__ == '__main__':
    main()
