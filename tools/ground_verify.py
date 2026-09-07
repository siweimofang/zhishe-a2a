# -*- coding: utf-8 -*-
"""ground_verify.py — KB编辑批 pre/post blob 独立地面终验（判定线复用）

假设: autocrlf仓, knowledge.json 盘上CRLF行间/末尾无换行, blob纯LF态,
      json重dump口径 ensure_ascii=False + indent=1 + LF→CRLF归一。

用法:
  python tools/ground_verify.py --pre 4071feb --post 3b6737d \
      --fixlist <fixlist.json> [--bak-pre <pre态BAK.json>] \
      [--expect-pre-sha 950e536a] [--expect-post-sha 32ae65d2] \
      [--entries 29788] [--anchors <anchors.json>]

断言集:
  A1 pre/post blob sha 与 --expect-*-sha 相符(如给, 支持短sha前缀)
  A2 pre blob(LF)→CRLF == --bak-pre 字节全等(如给)
  A3 post blob(LF)→CRLF == 现盘 knowledge.json 字节全等(仅 post==HEAD 时自动生效)
  A4 pre态每op old 在该(id,field)内 count==1
  A5 (pre + fixlist序替) 重放 == post blob (CRLF归一字节全等)
  A6 post entries数 == --entries (如给)
  A7 --anchors 现态抽查(如给): JSON数组 [id, field, 子串, 期望bool] × n

退出码: 0=全绿, 1=有红。--anchors 示例:
  [["k23268","answer","榫接在一起",true], ["k14630","question","未窗台板",false]]
"""
import argparse, json, subprocess, sys
sys.stdout.reconfigure(errors='replace')

ap = argparse.ArgumentParser()
ap.add_argument('--repo', default='.', help='仓库路径(默认当前目录)')
ap.add_argument('--pre', required=True, help='pre态commit(短sha可)')
ap.add_argument('--post', required=True, help='post态commit')
ap.add_argument('--fixlist', required=True, help='执行件fixlist JSON路径')
ap.add_argument('--bak-pre', help='pre态盘上BAK路径(如给则做A2)')
ap.add_argument('--expect-pre-sha', help='pre blob sha(全或短前缀)')
ap.add_argument('--expect-post-sha', help='post blob sha')
ap.add_argument('--entries', type=int, help='post entries数断言')
ap.add_argument('--anchors', help='现态锚JSON路径')
a = ap.parse_args()

fails = []
def check(name):
    def deco(fn):
        try:
            fn()
            print(f'[PASS] {name}')
        except AssertionError as ex:
            fails.append(name); print(f'[FAIL] {name}: {ex}')
        except Exception as ex:
            fails.append(name); print(f'[FAIL] {name}: {type(ex).__name__}: {ex}')
    return deco

def blob_at(commit):
    r = subprocess.run(['git', '-C', a.repo, 'show', f'{commit}:data/knowledge.json'], capture_output=True)
    assert r.returncode == 0, f'git show {commit}:data/knowledge.json 失败: {r.stderr.decode(errors="replace")[:200]}'
    return r.stdout

def rev(commit):
    r = subprocess.run(['git', '-C', a.repo, 'rev-parse', f'{commit}:data/knowledge.json'], capture_output=True)
    assert r.returncode == 0
    return r.stdout.decode().strip()

def crlf(b):
    t = b.decode('utf-8')
    assert '\r' not in t, 'blob含CR(应为纯LF态)'
    return t.replace('\n', '\r\n').encode('utf-8')

def dumpcrlf(entries):
    d = json.dumps(entries, ensure_ascii=False, indent=1)
    assert '\r' not in d
    return d.replace('\n', '\r\n').encode('utf-8')

def sha_match(got, want):
    return bool(want) and (got == want or got.startswith(want) or want.startswith(got))

b_pre, b_post = blob_at(a.pre), blob_at(a.post)
pre_sha, post_sha = rev(a.pre), rev(a.post)
print(f'pre  {a.pre}  blob={pre_sha}')
print(f'post {a.post} blob={post_sha}')

@check('A1 pre/post blob sha 与期望相符')
def _A1():
    if not (a.expect_pre_sha or a.expect_post_sha):
        print('       (未给期望sha, 仅打印)'); return
    if a.expect_pre_sha:
        assert sha_match(pre_sha, a.expect_pre_sha), f'pre blob {pre_sha} != {a.expect_pre_sha}'
    if a.expect_post_sha:
        assert sha_match(post_sha, a.expect_post_sha), f'post blob {post_sha} != {a.expect_post_sha}'

@check('A2 pre blob→CRLF == bak-pre 字节全等')
def _A2():
    if not a.bak_pre:
        print('       (未给BAK, 跳过)'); return
    with open(a.bak_pre, 'rb') as f:
        d = f.read()
    assert crlf(b_pre) == d, f'{len(crlf(b_pre))}B vs BAK {len(d)}B'

@check('A3 post blob→CRLF == 现盘字节全等')
def _A3():
    head = subprocess.run(['git', '-C', a.repo, 'rev-parse', 'HEAD:data/knowledge.json'],
                          capture_output=True).stdout.decode().strip()
    if head != post_sha:
        print(f'       (post {post_sha[:8]} != HEAD {head[:8]}, 跳过现盘比对)'); return
    with open(a.repo.rstrip('/\\') + '/data/knowledge.json', 'rb') as f:
        d = f.read()
    assert crlf(b_post) == d, '现盘 != post blob(CRLF)'

@check('A4 pre态每op old在该(id,field)内count==1')
def _A4():
    global pre_entries, ops
    with open(a.fixlist, 'rb') as f:
        ops = json.loads(f.read().decode('utf-8'))['fixlist']
    pre_entries = json.loads(b_pre.decode('utf-8'))
    idx = {e['id']: e for e in pre_entries}
    for i, op in enumerate(ops):
        e = idx.get(op['id'])
        assert e, f'op{i} 条目缺失 {op["id"]}'
        c = e[op['field']].count(op['old'])
        assert c == 1, f'op{i} {op["id"]}.{op["field"]} count={c}'

@check('A5 pre+fixlist重放 == post blob(CRLF归一)')
def _A5():
    idx = {e['id']: e for e in pre_entries}
    for op in ops:
        e = idx[op['id']]
        e[op['field']] = e[op['field']].replace(op['old'], op['new'])
    assert dumpcrlf(pre_entries) == crlf(b_post), '重放字节 != post blob'

@check('A6 post entries数')
def _A6():
    if a.entries is None:
        print('       (未给--entries, 跳过)'); return
    post_entries = json.loads(b_post.decode('utf-8'))
    assert len(post_entries) == a.entries, f'{len(post_entries)} != {a.entries}'

@check('A7 现态锚抽查')
def _A7():
    if not a.anchors:
        print('       (未给--anchors, 跳过)'); return
    with open(a.anchors, 'rb') as f:
        checks = json.loads(f.read().decode('utf-8'))
    idx = {e['id']: e for e in json.loads(b_post.decode('utf-8'))}
    for eid, fld, sub, want in checks:
        got = sub in idx[eid][fld]
        assert got == bool(want), f'{eid}.{fld} 「{sub}」 got={got} want={want}'
    print(f'       ({len(checks)}项全过)')

print(f'GROUND {"ALL GREEN" if not fails else "RED: " + ",".join(fails)}')
sys.exit(0 if not fails else 1)
