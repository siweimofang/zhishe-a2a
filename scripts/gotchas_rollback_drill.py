#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Gotchas 回滚演练脚本 (P2 · 可逆副作用运行时回归探针)
=====================================================
一键闭环验证热更新+回滚链路,任何一次部署/升级后可重复运行:

    热新增临时规则 → 业务检索命中 → 批次回滚 → 检索消失 → 状态复核

安全约定:
- 密钥从项目 .env 读取(A2A_API_KEY / A2A_ADMIN_KEY),不进命令行、不回显
- 演练规则命名 GZ-DRILL-<时间戳>、批次 drill-<时间戳>,与业务库隔离
- 演练结束必清理:即使中途失败也会在 finally 中回滚批次
- 演练不落盘:回滚后知识库总条数与演练前一致

用法:  python scripts/gotchas_rollback_drill.py [--base-url http://127.0.0.1:8765]
退出码: 0 = 全部通过 / 1 = 存在失败(报告已输出)
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# ── 常量 ──
DEFAULT_BASE = "http://127.0.0.1:8765"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
MARK = "演练专用磁砖临时规则"  # 独特词:title/answer/question 均携带,保证检索可命中
DRILL_PREFIX = "GZ-DRILL-"


def load_env_keys() -> tuple:
    """从 .env 读取双密钥(不存在则空串)。"""
    biz = admin = ""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("A2A_API_KEY="):
                biz = line.split("=", 1)[1].strip()
            elif line.startswith("A2A_ADMIN_KEY="):
                admin = line.split("=", 1)[1].strip()
    return biz, admin


def api(base: str, method: str, path: str, biz: str, admin: str, body=None, timeout=15):
    """发请求,返回 (status, json)。密钥只进请求头,绝不打印。"""
    url = base + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + biz)
    req.add_header("X-Admin-Key", admin)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return e.code, {"detail": raw[:200]}
    except urllib.error.URLError as e:
        return 0, {"detail": f"无法连接 {base}: {e.reason}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Gotchas 回滚演练(可重复运行的回归探针)")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help=f"后端地址(默认 {DEFAULT_BASE})")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    biz, admin = load_env_keys()
    if not biz or not admin:
        print("[预检] FAIL: 项目 .env 缺少 A2A_API_KEY 或 A2A_ADMIN_KEY")
        return 1

    ts = str(int(time.time()))[-6:]
    ku_id = DRILL_PREFIX + ts
    batch_id = "drill-" + ts
    mark = MARK

    steps: list = []
    def step(name: str, ok: bool, detail: str = ""):
        steps.append((name, ok, detail))
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {name}" + (f"  {detail}" if detail else ""))

    print("=" * 60)
    print("Gotchas 回滚演练开始")
    print(f"  目标: {base}   演练规则: {ku_id}   批次: {batch_id}")
    print("=" * 60)

    # 1. 预检:管理面可达
    st, body = api(base, "GET", "/gotchas/admin/status", biz, admin)
    if st != 200 or "runtime_ready" not in body:
        step("预检:管理端点可达", False, f"HTTP {st} {body.get('detail', '')}")
        return 1
    if not body.get("runtime_ready"):
        step("预检:可逆副作用运行时就绪", False, "runtime_ready=false")
        return 1
    total_before, stack_before = body.get("total_kus"), body.get("effects_stack")
    step("预检:管理端点可达且运行时就绪", True, f"总条数 {total_before} · 栈 {stack_before}")

    # 2. 热新增临时规则
    ku = {
        "ku_id": ku_id,
        "title": f"【演练】{mark}",
        "question": [f"{mark} 怎么避坑", f"临时规则 {ku_id}"],
        "answer": f"这是回滚演练脚本自动创建的临时规则({ku_id}),演练结束后自动回滚,不代表真实知识。{mark}",
        "severity": "中",
        "trade": "演练",
        "stage": "施工",
        "knowledge_type": "gotcha",
    }
    st, body = api(base, "POST", "/gotchas/admin/rules", biz, admin,
                   {"ku": ku, "batch_id": batch_id})
    if st != 200 or body.get("state") != "APPLIED" or not body.get("effect_id"):
        step("热新增临时规则", False, f"HTTP {st} {body.get('detail', body)}")
        rollback_cleanup(base, biz, admin, batch_id)
        return 1
    eff_id = body["effect_id"]
    step("热新增临时规则", True, f"effect_id={eff_id} · 已生效")

    try:
        # 3. 业务检索命中
        q = urllib.parse.quote(mark)
        st, body = api(base, "GET", f"/gotchas/search?q={q}&limit=5", biz, admin)
        hit = False
        if st == 200:
            for r in body.get("results", []):
                if (r.get("ku") or {}).get("ku_id") == ku_id or ku_id in json.dumps(r, ensure_ascii=False):
                    hit = True
                    break
        step("业务检索命中临时规则", hit, "引擎 " + body.get("engine", "?") if st == 200 else f"HTTP {st}")

        # 4. 批次回滚
        st, body = api(base, "POST", "/gotchas/admin/rollback", biz, admin, {"batch_id": batch_id})
        ok = st == 200 and body.get("ok") is True
        step("批次回滚", ok, f"mode={body.get('mode')} ok={body.get('ok')}" if st == 200 else f"HTTP {st}")

        # 5. 检索消失(可逆性)
        gone = False
        if ok:
            st2, body2 = api(base, "GET", f"/gotchas/search?q={q}&limit=5", biz, admin)
            if st2 == 200:
                found = any((r.get("ku") or {}).get("ku_id") == ku_id
                            for r in body2.get("results", []))
                gone = not found
        step("回滚后检索消失(可逆性)", gone)

        # 6. 状态复核(汇流性:无残留)
        st3, body3 = api(base, "GET", "/gotchas/admin/status", biz, admin)
        clean = st3 == 200 and body3.get("total_kus") == total_before and body3.get("effects_stack") == stack_before
        step("状态复核:条数与栈回到演练前", clean,
             f"total {body3.get('total_kus')}→{total_before} · stack {body3.get('effects_stack')}→{stack_before}" if st3 == 200 else f"HTTP {st3}")

    finally:
        # 兜底清理:任何异常/失败路径都确保批次已回滚
        st, body = api(base, "POST", "/gotchas/admin/rollback", biz, admin, {"batch_id": batch_id})
        if not (st == 200 and body.get("ok") is True):
            print("[清理] 注意:批次回滚未成功(可能已回滚,幂等无害),请到运维面板核查")

    passed = sum(1 for s in steps if s[1])
    print("=" * 60)
    print(f"演练结束: {passed}/{len(steps)} 通过")
    if passed == len(steps):
        print("结论: 热更新+回滚链路健康,可逆副作用运行时工作正常")
        return 0
    for name, ok, detail in steps:
        if not ok:
            print(f"  断点: {name} {detail}")
    print("结论: 存在失败,请结合断点信息排查")
    return 1


def rollback_cleanup(base: str, biz: str, admin: str, batch_id: str) -> None:
    """步骤 2 失败时的清理(规则已登记但响应异常)。"""
    try:
        api(base, "POST", "/gotchas/admin/rollback", biz, admin, {"batch_id": batch_id})
        print("[清理] 已尝试回滚批次")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
