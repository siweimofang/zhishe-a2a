# -*- coding: utf-8 -*-
"""
P2 Step3 评分: 真值库 vs AI 预填结果 → 四指标报告
用法: python score_p2.py --prefill results/prefill_<ts>.json
指标(立项书口径):
  报价单侧: 条目召回率 / 单价提取准确率(±1%) / 坑命中率 / 误报率
  合同侧:   字段提取准确率(数字±5%, 枚举精确) / 规则命中混淆(命中率+误报率)
"""
import argparse, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEV_WARNING = ('warning_high', 'warning_low', 'warning')


def close_num(a, b, tol=0.05):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= tol


def resolve_sid(results, sid):
    """真值 sid → 结果 job id: 兼容 '#rN' 后缀与 repeat-1 无后缀两种形态"""
    if sid in results:
        return sid
    base = sid.split('#')[0]
    if '#' in sid and base in results:
        return base
    if '#' not in sid and f'{sid}#r1' in results:
        return f'{sid}#r1'
    return None


def assign_items(rows, items):
    """P6: (名,价)联合贪心匹配——仅用于价格对拍。

    旧口径 first-match 的缺陷: 同名行(瓷砖地砖×15、门及门套×6)全部对到第一个
    同名 AI 条目,对价被系统性记错。新口径: 有价真值行按价距升序贪心 1:1 分配,
    每条 AI 条目最多被消耗一次;无分配对时调用方回退 first-match。
    注意: 召回/坑命中不走本分配(保持旧 any-match 口径可与历史直比)——
    严格 1:1 消耗叠加上双向子串匹配会让短泛名真值行跨名抢条目(0904实踩:
    召回 94→55、坑 4/4→2/4)。
    返回 {真值行下标: 分配到的AI条目};未分配的真值行不在字典中。
    """
    pairs = []  # (unpriced_flag, dist, 真值行下标, AI条目下标)
    for ri, r in enumerate(rows):
        te = r['truth_entry'].strip()
        tp = r.get('truth_price', '').strip()
        for ii, it in enumerate(items):
            n = str(it.get('item') or '')
            if te in n or n in te:
                if tp:
                    try:
                        d = abs(float(it.get('unit_price')) - float(tp)) / max(abs(float(tp)), 1e-9)
                    except (TypeError, ValueError):
                        d = 9.9
                    pairs.append((0, d, ri, ii))
                else:
                    pairs.append((1, 0.0, ri, ii))
    pairs.sort(key=lambda p: (p[0], p[1]))
    assigned = {}
    used = set()
    for _flag, _d, ri, ii in pairs:
        if ri in assigned or ii in used:
            continue
        assigned[ri] = items[ii]
        used.add(ii)
    return assigned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prefill', required=True)
    args = ap.parse_args()
    results = {x['id']: x for x in json.load(open(os.path.join(HERE, args.prefill), encoding='utf-8'))}
    lines = ['# P2 Step3 评分报告', '']

    # ---------- 合同侧 ----------
    fc = os.path.join(HERE, 'truth_contract.csv')
    if os.path.isfile(fc):
        pairs = []
        for row in csv.DictReader(open(fc, encoding='utf-8-sig')):
            jid = resolve_sid(results, row['sample_id'])
            if not jid:
                continue
            x = results[jid]
            cl = (x.get('result') or {}).get('clauses') or {}
            au = (x.get('result') or {}).get('audit') or {}
            pairs.append((row, cl, au))
        lines.append(f'## 合同侧(样本 {len(pairs)})')
        if pairs:
            # ai_k = clauses 真实字段名; t_k = CSV truth 列名
            num_fields = [('total_price', 'truth_total'), ('deposit_percent', 'truth_deposit_pct'),
                          ('warranty_general', 'truth_warranty'), ('warranty_waterproof', 'truth_waterproof'),
                          ('addition_percent', 'truth_addition_cap'), ('duration_days', 'truth_duration')]
            tot = ok = 0
            per_field = {}
            for row, cl, _ in pairs:
                for ai_k, t_k in num_fields:
                    tv = row.get(t_k, '').strip()
                    if tv == '':
                        continue
                    tot += 1
                    good = close_num(cl.get(ai_k), float(tv.replace(',', '')))
                    ok += good
                    per_field.setdefault(t_k, [0, 0])
                    per_field[t_k][0] += good
                    per_field[t_k][1] += 1
            enum_fields = [('material_lock_level', 'truth_material_lock'), ('dispute_method', 'truth_dispute')]
            for row, cl, _ in pairs:
                for ai_k, t_k in enum_fields:
                    tv = row.get(t_k, '').strip()
                    if tv == '':
                        continue
                    tot += 1
                    good = str(cl.get(ai_k) or '') == tv
                    ok += good
                    per_field.setdefault(t_k, [0, 0])
                    per_field[t_k][0] += good
                    per_field[t_k][1] += 1
            acc = ok / tot if tot else 0
            lines.append(f'- 字段提取准确率: {ok}/{tot} = {acc:.1%}')
            for k, (g, t) in sorted(per_field.items()):
                lines.append(f'  - {k}: {g}/{t}')
            tp = fp = fn = 0
            for row, _, au in pairs:
                truth_rules = set(filter(None, row.get('truth_risk_rules', '').split(';')))
                ai_rules = set(r['rule'] for r in (au.get('risks') or []))
                tp += len(truth_rules & ai_rules)
                fp += len(ai_rules - truth_rules)
                fn += len(truth_rules - ai_rules)
            if tp + fn:
                lines.append(f'- 规则命中率(召回): {tp}/{tp+fn} = {tp/(tp+fn):.1%}')
            if tp + fp:
                lines.append(f'- 规则误报率: {fp}/{tp+fp} = {fp/(tp+fp):.1%}')
            lines.append(f'- 混淆: TP={tp} FP={fp} FN={fn}  (FP 逐案核对是提取误差还是规则阈值问题)')
        lines.append('')

    # ---------- 报价单侧 ----------
    fq = os.path.join(HERE, 'truth_quote.csv')
    if os.path.isfile(fq):
        truth = [r for r in csv.DictReader(open(fq, encoding='utf-8-sig'))]
        groups = {}  # 解析后的 job id → 真值行(同一结果只扫一次 FP, 真值行逐行计召回)
        for r in truth:
            jid = resolve_sid(results, r['sample_id'])
            if not jid:
                continue
            groups.setdefault(jid, []).append(r)
        tot_truth = recalled = price_ok = price_n = pits = hits = 0
        false_pos = 0
        for jid, rows in groups.items():
            x = results[jid]
            rep = (x.get('result') or {}).get('report') or {}
            items = rep.get('results') or []
            ai_items = [str(i.get('item') or '') for i in items]
            missing = [str(m) for m in (rep.get('missing_items') or [])]
            assigned = assign_items(rows, items)  # P6: (名,价)1:1贪心——仅用于价格对拍
            for ri, r in enumerate(rows):
                te = r['truth_entry'].strip()
                tot_truth += 1
                first_any = next((i for i in items if te in str(i.get('item') or '') or str(i.get('item') or '') in te), None)
                cand = assigned.get(ri) or first_any
                if first_any is not None:
                    recalled += 1
                    if r.get('truth_price', '').strip():
                        price_n += 1
                        price_ok += close_num(cand.get('unit_price'), r['truth_price'], 0.01)
                if r.get('is_pit', '').strip() == '1':
                    pits += 1
                    pit_hit = first_any is not None and str(first_any.get('status', '')).startswith('warning')
                    if not pit_hit and r.get('pit_type', '') == 'missing' and any(te in m or m in te for m in missing):
                        pit_hit = True
                    hits += pit_hit
            for i in items:
                if str(i.get('status', '')).startswith('warning'):
                    matched = any((r['truth_entry'].strip() in str(i.get('item') or '')) and r.get('is_pit', '').strip() == '1'
                                  for r in rows)
                    if not matched:
                        false_pos += 1
        lines.append(f'## 报价单侧(样本 {len(groups)})')
        if tot_truth:
            lines.append(f'- 条目召回率: {recalled}/{tot_truth} = {recalled/tot_truth:.1%}')
        if price_n:
            lines.append(f'- 单价提取准确率(±1%): {price_ok}/{price_n} = {price_ok/price_n:.1%}')
        if pits:
            lines.append(f'- 坑命中率: {hits}/{pits} = {hits/pits:.1%}')
        if false_pos:
            lines.append(f'- 误报(无坑报坑): {false_pos} 处')
        lines.append('')
    lines.append('---')
    lines.append('口径: 命中/误报逐案核对后再定阈值调整; FP 聚类分析优先于改阈值(防过拟合样张)。')
    out = os.path.join(HERE, 'results', f'score_{os.path.basename(args.prefill).replace("prefill_", "").replace(".json", "")}.md')
    open(out, 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines))
    print(f'\n报告: {out}')


if __name__ == '__main__':
    main()
