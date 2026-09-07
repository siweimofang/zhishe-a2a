# -*- coding: utf-8 -*-
# RN14盲区补丁 k3655 锤人→锤入 (gen段): 1op DE14补丁式
# 补丁令: _k3655_patch_notice.txt (md5=613a2bbe4c6a11c3d2f9e1248a948b5a 已验)
# pre基线对不上先停手; 全库census锤人仅此1处; 长窗锤人油灰唯一自证
import json, io, os, sys, hashlib, subprocess
sys.stdout.reconfigure(errors='replace')
sys.path.insert(0, r'C:\Users\Administrator\.qoderworkcn\workspace\msklrypny7w2454t')
import rn14_resolve as R

WS = R.WS
REPO = R.REPO
OUT_DIR = r'D:\projects\非默认outputs'
FIX_WS = os.path.join(WS, 'rn_patch_k3655_fixlist.json')
REP = os.path.join(WS, 'rn14_k3655_gen_report.txt')
L = []
def log(s):
    L.append(s); print(s)

# ---- 0. pre基线逐项比对 (补丁令第三节, 对不上停手) ----
EXPECT_HEAD = '614a5c1a56dae77fd032a332a5b2f20f5daee261'
EXPECT_BLOB = '40afa17a258db6009594ae7e88a9a4c1cf664d4f'
EXPECT_SHA256 = '5eb9be1070192d4a33a3f6205a7be11036fc2c3753a2625e6ea41319467794bd'
head = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD'], capture_output=True).stdout.decode().strip()
blob = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD:data/knowledge.json'], capture_output=True).stdout.decode().strip()
st = subprocess.run(['git', '-C', REPO, 'status', '--porcelain', '--', 'data/knowledge.json'], capture_output=True).stdout.decode().strip()
assert head == EXPECT_HEAD, 'HEAD漂移 %s' % head
assert blob == EXPECT_BLOB, 'blob漂移 %s' % blob
assert st == '', 'knowledge.json盘上有未提交态 %r' % st
raw, text, entries = R.load_kb()
assert hashlib.sha256(raw).hexdigest() == EXPECT_SHA256, 'sha256漂移'
assert len(raw) == 39248524 and len(entries) == 29788
idx = {e['id']: e for e in entries}
assert len(idx) == len(entries)
log('0 pre基线 OK: HEAD=614a5c1 blob=40afa17a sha256=5eb9be10...94bd bytes=39248524 entries=29788 盘净')

# ---- 1. census: 全库锤人仅此1处(k3655.answer), 同条目互证 ----
hits = []
for e in entries:
    for f in ('question', 'answer'):
        t = e.get(f) or ''
        if '锤人' in t:
            hits.append((e['id'], f, t.count('锤人')))
assert hits == [('k3655', 'answer', 1)], '全库锤人census异常 %s' % hits
fa = idx['k3655']['answer']
fq = idx['k3655'].get('question') or ''
assert fa.count('锤人') == 1 and fa.count('锤入') == 0 and fq.count('锤人') == 0
assert fa.count('锤人油灰') == 1 and fa.count('锤入油灰') == 0, '长窗锚不唯一'
assert fa.count('钉人') == 0 and fa.count('钉入') == 1, '同条目互证失败(钉人应已RN14修为钉入)'
i = fa.find('锤人油灰')
log('1 census OK: 全库锤人=k3655.answer x1; 长窗锤人油灰唯一; 钉入=1互证')
log('  ctx: %r' % fa[max(0, i - 16):i + 20])

# ---- 2. op构建(长窗锚) + 仿真 ----
op = {'id': 'k3655', 'field': 'answer', 'old': '锤人油灰', 'new': '锤入油灰'}
assert fa.count(op['old']) == 1 and op['old'] != op['new'] and len(op['old']) == len(op['new'])
sim = fa.replace(op['old'], op['new'], 1)
assert sim.count('锤人') == 0 and sim.count('锤入') == 1 and sim.count('锤入油灰') == 1
assert '锤人' not in sim
log('2 仿真 OK: 锤人=0 锤入=1(锤入油灰内在场)')

# ---- 3. fixlist双路落盘(字节全等) ----
fix = {
    'meta': {
        'batch': 'RN14盲区补丁 k3655 锤人→锤入 (9片眼筛漏筛位, 判定线定谳, 用户拍板)',
        'notice': '_k3655_patch_notice.txt md5=613a2bbe4c6a11c3d2f9e1248a948b5a',
        'pre_state': {'HEAD': EXPECT_HEAD, 'blob': EXPECT_BLOB, 'sha256': EXPECT_SHA256,
                      'bytes': 39248524, 'entries': 29788},
        'craft': '1op长窗锚锤人油灰(唯一)自证; 三态判定照旧; 全库census锤人=1(k3655.answer)→修后0',
    },
    'expect': {'numstat': '以实态diff为准', 'entries': 1, 'ops': 1, 'points': 1,
               'post_census': {'全库锤人': 0, 'k3655.锤入': 1, 'k3655.锤入油灰': 1}},
    'fixlist': [op],
}
def dumps_crlf(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1).replace('\n', '\r\n')
blob_ws = dumps_crlf(fix).encode('utf-8')
with io.open(FIX_WS, 'wb') as f:
    f.write(blob_ws)
p_out = os.path.join(OUT_DIR, '修复微批_k3655盲区补丁1op_fixlist_20260907.json')
with io.open(p_out, 'wb') as f:
    f.write(blob_ws)
with io.open(p_out, 'rb') as f:
    assert f.read() == blob_ws, '双路字节不等'
# 回读自证
reread = json.loads(io.open(FIX_WS, encoding='utf-8').read())
assert reread['fixlist'] == [op] and reread['expect']['ops'] == 1
log('3 fixlist双路落盘字节全等 (%dB): %s' % (len(blob_ws), p_out))

# ---- 4. ledger留档(累计账: RN14 1454条 + 本补丁1条 = 1455) ----
ledger = {
    'batch': 'RN14盲区补丁k3655', 'date': '2026-09-07',
    'records': [{'gid': 'PATCH-k3655-01', 'id': 'k3655', 'fld': 'answer',
                 'op': '锤人→锤入', 'window': '锤人油灰→锤入油灰',
                 'evidence': '判定线22:4x全库census唯一; 钉入=1同条目互证; OCR人→入高置信(钉子锤入油灰内)',
                 'status': 'EXEC', 'pre_census_全库锤人': 1}],
    'cumulative': {'RN14主批': 1454, '本补丁': 1, '累计': 1455},
}
with io.open(os.path.join(OUT_DIR, 'RN14盲区补丁k3655_ledger_20260907.json'), 'w', encoding='utf-8') as f:
    json.dump(ledger, f, ensure_ascii=False, indent=1)
log('4 ledger留档 OK (累计1455条)')
log('K3655_GEN_GREEN')
with io.open(REP, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print('GEN_DONE ->', REP)
