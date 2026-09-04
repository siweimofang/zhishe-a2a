# -*- coding: utf-8 -*-
"""
P2 Step3 真值入库: 校验人工回填的 confirm CSV → 追加真值库(防重)
用法: python ingest_p2.py --ts 0904_HHMM     # 处理 contract_confirm_<ts>.csv / quote_confirm_<ts>.csv
校验失败整体中止, 不写半截数据(P30 惯例)。
"""
import argparse, csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRUTH_CONTRACT = os.path.join(HERE, 'truth_contract.csv')
TRUTH_QUOTE = os.path.join(HERE, 'truth_quote.csv')
MANIFEST = os.path.join(HERE, 'MANIFEST_P2.md')

CONTRACT_NUM_FIELDS = ['total', 'deposit_pct', 'warranty', 'waterproof', 'addition_cap', 'duration']
CONTRACT_ENUM_FIELDS = {'material_lock': ['brand_model', 'brand', 'equivalent', 'none'],
                        'dispute': ['arbitration', 'litigation']}


def num(v):
    v = str(v).strip()
    if v == '':
        return None
    return float(v.replace(',', ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ts', required=True, help='confirm CSV 时间戳, 如 0904_2230')
    args = ap.parse_args()

    fc = os.path.join(HERE, f'contract_confirm_{args.ts}.csv')
    fq = os.path.join(HERE, f'quote_confirm_{args.ts}.csv')
    errors, contract_rows, quote_rows = [], [], []

    if os.path.isfile(fc):
        for row in csv.DictReader(open(fc, encoding='utf-8-sig')):
            sid = row['sample_id'].strip()
            if not row.get('truth_total', '').strip() and not row.get('truth_risk_rules', '').strip():
                errors.append(f'{sid}: truth_total 与 truth_risk_rules 至少填一项')
                continue
            for f in CONTRACT_NUM_FIELDS:
                col = f'truth_{f}'
                if row.get(col, '').strip():
                    try:
                        num(row[col])
                    except ValueError:
                        errors.append(f'{sid}: {col}={row[col]} 不是数字')
            for f, allowed in CONTRACT_ENUM_FIELDS.items():
                v = row.get(f'truth_{f}', '').strip()
                if v and v not in allowed:
                    errors.append(f'{sid}: truth_{f}={v} 不在 {allowed}')
            contract_rows.append(row)

    if os.path.isfile(fq):
        for row in csv.DictReader(open(fq, encoding='utf-8-sig')):
            sid = row['sample_id'].strip()
            if not row.get('truth_entry', '').strip():
                continue  # AI 提取多余行, 用户可不填(=该条目真值不存在, 记误报候选)
            if row.get('truth_price', '').strip() == '':
                errors.append(f'{sid}/{row.get("truth_entry")}: truth_price 未填')
                continue
            if row.get('is_pit', '').strip() and row['is_pit'].strip() not in ('0', '1'):
                errors.append(f'{sid}: is_pit 只能 0/1')
            quote_rows.append(row)

    if errors:
        print(f'校验失败 {len(errors)} 处, 整体中止(未写入任何数据):')
        for e in errors[:20]:
            print('  -', e)
        sys.exit(1)

    def append(path, rows, header):
        exists = os.path.isfile(path)
        old_keys = set()
        if exists:
            for r in csv.DictReader(open(path, encoding='utf-8-sig')):
                old_keys.add((r['sample_id'], r.get('truth_entry', '')))
        fresh = [r for r in rows if (r['sample_id'], r.get('truth_entry', '')) not in old_keys]
        with open(path, 'a', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction='ignore')
            if not exists:
                w.writeheader()
            w.writerows(fresh)
        return len(fresh)

    n1 = n2 = 0
    if contract_rows:
        n1 = append(TRUTH_CONTRACT, contract_rows, list(contract_rows[0].keys()))
    if quote_rows:
        n2 = append(TRUTH_QUOTE, quote_rows, list(quote_rows[0].keys()))

    with open(MANIFEST, 'a', encoding='utf-8') as f:
        f.write(f'- ingest: 合同 {n1} 行 / 报价 {n2} 行入库(校验通过, 重复已去重)\n')
    print(f'入库完成: 合同 {n1} 行 → truth_contract.csv | 报价 {n2} 行 → truth_quote.csv')
    print('下一步: python score_p2.py --prefill results/prefill_<ts>.json')


if __name__ == '__main__':
    main()
