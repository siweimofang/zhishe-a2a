# -*- coding: utf-8 -*-
# 埋→理补漏微批 (gen段): 挂账5位, RN14回归门现态实测残留, 用户"继续"拍板(k3655先例)
# 范围锁死5位: k4347/k12427/k18474 预理 + k3675/k17349 理设; k4224疑点不动
import json, io, os, sys, hashlib, subprocess
sys.stdout.reconfigure(errors='replace')
sys.path.insert(0, r'C:\Users\Administrator\.qoderworkcn\workspace\msklrypny7w2454t')
import rn14_resolve as R

WS = R.WS
REPO = R.REPO
OUT_DIR = r'D:\projects\非默认outputs'
FIX_WS = os.path.join(WS, 'rn_patch_ml5_fixlist.json')
REP = os.path.join(WS, 'rn14_ml5_gen_report.txt')
L = []
def log(s):
    L.append(s); print(s)

# ---- 0. pre基线(=k3655 post盘: HEAD f47bf4c / blob 9d58facc) ----
EXPECT_HEAD = 'f47bf4c0cdc6720237704e602e472a709f8c1c1f'
EXPECT_BLOB = '9d58faccef31cca1f911a6ba96612d57d236bef7'
EXPECT_SHA256_PFX = '30c7c120d738c363'
head = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD'], capture_output=True).stdout.decode().strip()
blob = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD:data/knowledge.json'], capture_output=True).stdout.decode().strip()
st = subprocess.run(['git', '-C', REPO, 'status', '--porcelain', '--', 'data/knowledge.json'], capture_output=True).stdout.decode().strip()
assert head == EXPECT_HEAD and blob == EXPECT_BLOB and st == '', '基线漂移 %s %s %r' % (head, blob, st)
raw, text, entries = R.load_kb()
sha = hashlib.sha256(raw).hexdigest()
assert sha.startswith(EXPECT_SHA256_PFX), 'sha256漂移 %s' % sha
assert len(raw) == 39248524 and len(entries) == 29788
idx = {e['id']: e for e in entries}
log('0 pre基线 OK: HEAD=f47bf4c blob=9d58facc sha256=%s bytes=39248524 entries=29788 盘净' % sha[:16])

# ---- 1. 5位锚定硬断言 + 全库census基线 ----
SITES = [
    ('k4347',  'answer', '预理工作', '预埋工作'),
    ('k12427', 'answer', '预理工作', '预埋工作'),
    ('k18474', 'answer', '预留、预理', '预留、预埋'),
    ('k3675',  'answer', '理设前',   '埋设前'),
    ('k17349', 'answer', '理设管线', '埋设管线'),
]
EV = {'k4347': '同条目预埋=2(埋理0907批已修预埋的木框架); 电气配管及配线的埋设工作', 
      'k12427': '同条目预埋=1(埋理0907批已修预埋吊钩); 结构施工中做好预埋工作',
      'k18474': '标准词形: 幕墙预留、预埋固定搭配; 同条目无预埋(historic census漏网)',
      'k3675': '同条目预埋=17/埋件=16; 预埋件在埋设前应进行专项技术交底',
      'k17349': '标准词形: 埋设管线(墙体布管); 同条目无埋设(historic census漏网)'}
for kid, fld, old, new in SITES:
    f = idx[kid][fld]
    assert f.count(old) == 1, '%s 锚不唯一 %d' % (kid, f.count(old))
    assert f.count(new) == 0 and (idx[kid].get('question') or '').count(old) == 0
n_yl = sum((e.get(f) or '').count('预理') for e in entries for f in ('question', 'answer'))
n_ls = sum((e.get(f) or '').count('理设') for e in entries for f in ('question', 'answer'))
assert n_yl == 4 and n_ls == 61, 'census基线漂移 预理=%d 理设=%d' % (n_yl, n_ls)
assert sum((idx[k]['answer'] if f == 'answer' else idx[k]['question']).count(o)
           for k, f, o, n in SITES) == 5
log('1 5位锚全唯一(census基线 预理=4含k4224疑点/理设=61含59合法子串) OK')

# ---- 2. 仿真 ----
ops = [{'id': k, 'field': f, 'old': o, 'new': n} for k, f, o, n in SITES]
sim = {}
for op in ops:
    assert len(op['old']) == len(op['new'])
    cur = idx[op['id']][op['field']]
    assert cur.count(op['old']) == 1
    sim[(op['id'], op['field'])] = cur.replace(op['old'], op['new'], 1)
    assert sim[(op['id'], op['field'])].count(op['old']) == 0 and op['new'] in sim[(op['id'], op['field'])]
post_ls = n_ls - 2
post_yl = n_yl - 3
assert post_yl == 1 and post_ls == 59
log('2 仿真 OK: post全库 预理=1(k4224疑点) 理设=59(全合法子串)')

# ---- 3. fixlist双路落盘(字节全等) ----
fix = {
    'meta': {
        'batch': '埋→理补漏微批 5op (埋理0907批窗口式单点替换漏网, RN14回归门现态实测, 用户继续拍板)',
        'pre_state': {'HEAD': EXPECT_HEAD, 'blob': EXPECT_BLOB, 'sha256': sha, 'bytes': 39248524, 'entries': 29788},
        'craft': '最小唯一窗口count==1; 范围锁死5位; k4224疑点(预理孔洞)不动; 理设其余59处为合法子串(合理设计/处理设备/监理设施等)不动',
        'evidence': EV,
    },
    'expect': {'numstat': '以实态diff为准', 'entries': 5, 'ops': 5, 'points': 5,
               'post_census': {'全库预理': 1, '全库理设': 59}},
    'fixlist': ops,
}
blob_ws = json.dumps(fix, ensure_ascii=False, indent=1).replace('\n', '\r\n').encode('utf-8')
with io.open(FIX_WS, 'wb') as f:
    f.write(blob_ws)
p_out = os.path.join(OUT_DIR, '修复微批_埋理补漏5op_fixlist_20260907.json')
with io.open(p_out, 'wb') as f:
    f.write(blob_ws)
with io.open(p_out, 'rb') as f:
    assert f.read() == blob_ws
assert json.loads(io.open(FIX_WS, encoding='utf-8').read())['fixlist'] == ops
log('3 fixlist双路落盘字节全等 (%dB): %s' % (len(blob_ws), p_out))

# ---- 4. ledger ----
ledger = {
    'batch': '埋理补漏5op', 'date': '2026-09-07',
    'records': [{'gid': 'ML5-%02d' % (i + 1), 'id': k, 'fld': f, 'op': '%s→%s' % (o, n),
                 'evidence': EV[k], 'status': 'EXEC'} for i, (k, f, o, n) in enumerate(SITES)],
    'post_census': {'全库预理': 1, '全库理设': 59, 'k4224疑点': '保留不动'},
    'cumulative': {'埋理0907主批': 421, '本补漏': 5},
}
with io.open(os.path.join(OUT_DIR, '埋理补漏5op_ledger_20260907.json'), 'w', encoding='utf-8') as f:
    json.dump(ledger, f, ensure_ascii=False, indent=1)
log('4 ledger留档 OK')
log('ML5_GEN_GREEN')
with io.open(REP, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print('GEN_DONE ->', REP)
