# -*- coding: utf-8 -*-
"""
P2 Step3 评测预填脚本（P30 四段式: prefill→人工确认→ingest→score）
扫描 eval_inbox 脱敏样张 → 按前缀分派插件工具实跑 → 生成 confirm 包 + 双真值 CSV 骨架
用法:
  python prefill_p2.py                      # 处理 ../eval_inbox
  python prefill_p2.py --dir synthetic      # 处理指定子目录(dry-run/演练)
  python prefill_p2.py --repeat 3           # 同图跑3次(一致性观察)
样张命名约定: contract_*.png=合同 / quote_*.jpg=报价单, 无前缀跳过
"""
import argparse, csv, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
A2A = os.path.dirname(HERE)  # p2_eval 上一级 = zhishe-a2a(0904修正: 原取上两级落到千问AI Agent目录, .env永远找不到)
EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
TS = time.strftime('%m%d_%H%M')


def load_key():
    env = os.path.join(A2A, '.env')
    if os.path.isfile(env):
        for line in open(env, encoding='utf-8', errors='ignore'):
            line = line.strip()
            if line.startswith('DEEPSEEK_API_KEY='):
                v = line.split('=', 1)[1].strip().strip('"')
                if v:
                    return v
    return os.environ.get('DEEPSEEK_API_KEY', '')


def scan_inbox(d):
    # 0904 P1分页送审: 支持 __pNN 分页样张, 同组多页合并为一个样本(多图一次任务)
    # 例: quote_201_pingpin__p1.png..__p4.png → 样本 quote_201_pingpin(4页)
    groups = {'contract': [], 'quote': []}
    skipped = []
    for fn in sorted(os.listdir(d)):
        if not fn.lower().endswith(EXTS):
            continue
        low = fn.lower()
        p = os.path.abspath(os.path.join(d, fn))
        if low.startswith('contract_'):
            prefix = 'contract'
        elif low.startswith('quote_'):
            prefix = 'quote'
        else:
            skipped.append(fn)
            continue
        stem = os.path.splitext(fn)[0]
        m = re.match(r'^(.*?)__p(\d+)$', stem, re.IGNORECASE)
        gkey, pageno = (m.group(1), int(m.group(2))) if m else (stem, 0)
        for g in groups[prefix]:
            if g[0] == gkey:
                g[1].append((pageno, fn, p))
                break
        else:
            groups[prefix].append([gkey, [(pageno, fn, p)]])
    contracts = [(g[0], [x for _, _, x in sorted(g[1])]) for g in groups['contract']]
    quotes = [(g[0], [x for _, _, x in sorted(g[1])]) for g in groups['quote']]
    return contracts, quotes, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='eval_inbox', help='eval_inbox|synthetic|其他 p2_eval 下子目录')
    ap.add_argument('--repeat', type=int, default=1, help='每张图跑几次(>1 时检查提取一致性)')
    ap.add_argument('--city', default='', help='报价单样张城市(缺省不传)')
    ap.add_argument('--tier', default='', help='报价单样张档次(缺省不传)')
    args = ap.parse_args()

    src = os.path.join(HERE, args.dir)
    if not os.path.isdir(src):
        sys.exit(f'目录不存在: {src}')
    contracts, quotes, skipped = scan_inbox(src)
    if skipped:
        print(f'[提示] {len(skipped)} 张无 contract_/quote_ 前缀跳过: {", ".join(skipped[:5])}')
    if not contracts and not quotes:
        sys.exit('未发现可处理样张(命名须以 contract_/quote_ 开头,见收样SOP_P2.md)')

    jobs, ids = [], []
    cid = 100
    for gkey, pages in contracts:
        cid += 1
        sid = f'contract_{cid}'
        paths = list(pages)  # scan_inbox 已扁平化为路径列表
        label = gkey + (f'({len(paths)}页)' if len(paths) > 1 else '')
        ids.append((sid, label, 'hetong_shenhe'))
        for k in range(args.repeat):
            jobs.append({'id': f'{sid}#r{k+1}' if args.repeat > 1 else sid,
                         'tool': 'hetong_shenhe', 'args': {'contract_images': paths}})
    qid = 200
    extra = {k: v for k, v in (('city', args.city), ('tier', args.tier)) if v}
    for gkey, pages in quotes:
        qid += 1
        sid = f'quote_{qid}'
        paths = list(pages)  # scan_inbox 已扁平化为路径列表
        label = gkey + (f'({len(paths)}页)' if len(paths) > 1 else '')
        ids.append((sid, label, 'baojia_image_audit'))
        for k in range(args.repeat):
            jobs.append({'id': f'{sid}#r{k+1}' if args.repeat > 1 else sid,
                         'tool': 'baojia_image_audit', 'args': dict(images=paths, **extra)})

    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    jobs_f = os.path.join(HERE, 'results', f'jobs_{TS}.json')
    res_f = os.path.join(HERE, 'results', f'prefill_{TS}.json')
    json.dump(jobs, open(jobs_f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    env = {**os.environ, 'DEEPSEEK_API_KEY': load_key(), 'PYTHONIOENCODING': 'utf-8'}
    if not env['DEEPSEEK_API_KEY']:
        sys.exit('未找到 DEEPSEEK_API_KEY(.env 或环境变量)')
    print(f'共 {len(jobs)} 个任务(合同 {len(contracts)} / 报价单 {len(quotes)} × repeat {args.repeat}), 开始实跑...')
    r = subprocess.run(['node', os.path.join(HERE, 'eval_runner.mjs'), jobs_f, res_f],
                       env=env, cwd=HERE)
    if r.returncode != 0:
        sys.exit('eval_runner 失败')
    results = {x['id']: x for x in json.load(open(res_f, encoding='utf-8'))}

    def reps(sid):
        # repeat>1 时 eval_runner 写出的 id 带 #rN 后缀; repeat=1 时原样
        if args.repeat == 1:
            return [(sid, results.get(sid) or {})]
        return [(f'{sid}#r{k+1}', results.get(f'{sid}#r{k+1}') or {}) for k in range(args.repeat)]

    # ---- confirm 包(人读) ----
    md = [f'# P2 评测确认包 {TS}', '', f'来源目录: {args.dir} | repeat: {args.repeat}', '',
          '逐图核对 AI 提取值, 把真值填进同名 CSV 的 truth_* 列(只改 truth 列), 然后跑 ingest_p2.py。', '']
    for sid, fn, tool in ids:
        for rid, x in reps(sid):
            res = x.get('result') or {}
            md.append(f'## {rid} ({fn}) — {tool} → {res.get("status")} {x.get("ms")}ms')
            if tool == 'hetong_shenhe':
                cl = res.get('clauses') or {}
                au = res.get('audit') or {}
                md.append(f"- 提取: 总价={cl.get('total_price')} 定金%={cl.get('deposit_percent')} 保修={cl.get('warranty_general')}/{cl.get('warranty_waterproof')} "
                          f"增项封顶%={cl.get('addition_percent')} 材料锁={cl.get('material_lock_level')} 争议={cl.get('dispute_method')} 工期={cl.get('duration_days')} "
                          f"日违约金%={cl.get('delay_penalty_daily_percent')}")
                md.append(f"- PII: {(res.get('ocr') or {}).get('pii', {}).get('found')}")
                md.append(f"- 命中规则: {', '.join(r['rule'] for r in (au.get('risks') or [])) or '无'}")
                md.append(f"- tips: {', '.join(t.get('topic', '') for t in (res.get('tips') or [])) or '无'}")
            else:
                rep = res.get('report') or res
                items = rep.get('results') or []
                md.append(f"- 提取条目 {len(items)} 个, 漏项 {len(rep.get('missing_items') or [])}, 异常 "
                          f"{sum(1 for i in items if i.get('status', '').startswith('warning'))}")
                for it in items[:20]:
                    md.append(f"  - {it.get('item')} | 单价={it.get('unit_price')} | {it.get('status')} | 偏离={it.get('deviation')}")
            md.append('')
    open(os.path.join(HERE, 'results', f'confirm_eval_{TS}.md'), 'w', encoding='utf-8').write('\n'.join(md))

    # ---- CSV 骨架 ----
    qc = os.path.join(HERE, f'contract_confirm_{TS}.csv')
    with open(qc, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['sample_id', 'file', 'ai_total', 'truth_total', 'ai_deposit_pct', 'truth_deposit_pct',
                    'ai_warranty', 'truth_warranty', 'ai_waterproof', 'truth_waterproof',
                    'ai_addition_cap', 'truth_addition_cap', 'ai_material_lock', 'truth_material_lock',
                    'ai_dispute', 'truth_dispute', 'ai_duration', 'truth_duration',
                    'ai_risk_rules', 'truth_risk_rules', 'note'])
        for sid, fn, tool in ids:
            if not sid.startswith('contract_'):
                continue
            for rid, x in reps(sid):
                res = x.get('result') or {}
                cl = res.get('clauses') or {}
                au = res.get('audit') or {}
                w.writerow([rid, fn, cl.get('total_price'), '', cl.get('deposit_percent'), '',
                            cl.get('warranty_general'), '', cl.get('warranty_waterproof'), '',
                            cl.get('addition_percent'), '', cl.get('material_lock_level'), '',
                            cl.get('dispute_method'), '', cl.get('duration_days'), '',
                            ';'.join(r['rule'] for r in (au.get('risks') or [])), '', ''])
    qv = os.path.join(HERE, f'quote_confirm_{TS}.csv')
    with open(qv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['sample_id', 'file', 'ai_entry', 'ai_price', 'truth_entry', 'truth_price',
                    'truth_qty', 'truth_total', 'is_pit', 'pit_type', 'note'])
        for sid, fn, tool in ids:
            if not sid.startswith('quote_'):
                continue
            for rid, x in reps(sid):
                rep = (x.get('result') or {}).get('report') or {}
                for it in (rep.get('results') or []):
                    w.writerow([rid, fn, it.get('item'), it.get('unit_price'), '', '', '', '', '', '', ''])
    print(f'确认包: results/confirm_eval_{TS}.md')
    print(f'合同真值表: {qc}')
    print(f'报价真值表: {qv}')
    print('下一步: 人工核对 CSV truth_* 列 → python ingest_p2.py ' + f'--ts {TS}')


if __name__ == '__main__':
    main()
