#!/usr/bin/env python3
"""
审核 CLI：逐条审核待审区 KU，通过的升级入库并重建索引。

交互命令：
    y = 通过入库（升级到 REFERENCE）
    n = 丢弃
    e = 现场编辑后再决定
    s = 跳过（留在待审区下次再审）
    q = 退出（已审结果生效，未审保留）

用法：
    python run_review.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from annotator import config
from annotator import writer, rebuilder


def _display(entry: dict, idx: int, total: int) -> None:
    ku = entry["ku"]
    print("\n" + "─" * 60)
    print(f"[{idx + 1}/{total}] {ku.get('ku_id', '?')}  {ku.get('title', '')}")
    print("─" * 60)
    print(f"阶段: {ku.get('stage')}  严重度: {ku.get('severity')}  范围: {ku.get('scope', 'universal')}")
    print(f"角色: {ku.get('role')}  工种: {ku.get('trade')}  材料: {ku.get('material')}")
    print(f"问题类型: {ku.get('problem_type')}")
    print(f"\n【描述】{ku.get('description', '')}")
    if ku.get("typical_scenario"):
        print(f"\n【场景】{ku.get('typical_scenario')}")
    print(f"\n【避坑】{ku.get('how_to_avoid', '')}")
    hint = entry.get("duplicate_hint")
    if hint:
        print(f"\n⚠ 疑似重复：{hint.get('ku_id')} 《{hint.get('title')}》（{hint.get('reason')}）")
    if entry.get("source"):
        print(f"\n来源: {entry['source']}")


def _edit(ku: dict) -> None:
    """现场编辑关键字段（回车保留原值）。"""
    print("\n[编辑] 回车保留原值。")
    title = input(f"  标题 [{ku.get('title', '')}]: ").strip()
    if title:
        ku["title"] = title
    desc = input("  描述(可粘贴多行，单独一行 END 结束，直接回车保留原值): ").strip()
    if desc:
        if desc == "":
            pass
        ku["description"] = _read_multiline(desc)
    avoid = input("  避坑(同上规则，直接回车保留原值): ").strip()
    if avoid:
        ku["how_to_avoid"] = _read_multiline(avoid)
    sev = input(f"  严重度 [{ku.get('severity', '')}]: ").strip()
    if sev:
        ku["severity"] = sev


def _read_multiline(first_line: str) -> str:
    """支持多行输入，单独一行 END 结束。"""
    lines = [first_line]
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _upgrade(ku: dict) -> dict:
    """审核通过：升级质量等级与验证状态。"""
    today = date.today().isoformat()
    meta = ku.setdefault("metadata", {})
    meta["quality_level"] = config.QUALITY_ON_APPROVE
    meta["verified"] = True
    meta["verify_method"] = "human_review"
    meta["updated_at"] = today
    meta["last_reviewed_at"] = today
    return ku


def run() -> int:
    pending = writer.load_pending()
    if not pending:
        print("待审区为空，没有可审核的 KU。")
        return 0

    total = len(pending)
    print(f"待审区共 {total} 条 KU，开始审核（y通过/n丢弃/e编辑/s跳过/q退出）。")

    approved = []
    remaining = []
    discarded = 0
    i = 0
    while i < total:
        entry = pending[i]
        _display(entry, i, total)
        while True:
            try:
                cmd = input("\n> [y/n/e/s/q]: ").strip().lower()
            except EOFError:
                cmd = "q"
            if cmd == "y":
                approved.append(_upgrade(entry["ku"]))
                print(f"  ✓ 已通过 {entry['ku'].get('ku_id')}")
                break
            elif cmd == "n":
                discarded += 1
                print(f"  ✗ 已丢弃 {entry['ku'].get('ku_id')}")
                break
            elif cmd == "e":
                _edit(entry["ku"])
                _display(entry, i, total)
                continue
            elif cmd == "s":
                remaining.append(entry)
                print("  … 已跳过，保留待审。")
                break
            elif cmd == "q":
                # 保留当前及之后所有未审条目
                remaining.extend(pending[i:])
                print("  退出审核。")
                i = total  # 跳出外层
                break
            else:
                print("  请输入 y/n/e/s/q。")
        i += 1

    # ── 入库 ──
    if approved:
        backup = rebuilder.backup_all_ku()
        print(f"\n[备份] all_ku.json -> {backup}")
        merged = rebuilder.merge_kus(approved)
        stats = rebuilder.full_rebuild()
        print(f"[入库] 通过 {len(approved)} 条，库内总计 {len(merged)} 条。")
        print(f"[统计] RELIABLE+ = {stats['phase1_target']['current_reliable_plus']}，"
              f"阶段覆盖 {stats['coverage']['stages_covered']}，"
              f"工种覆盖 {stats['coverage']['trades_covered']}")

    # ── 回写待审区（剩余）──
    writer.save_pending(remaining)

    print("\n" + "=" * 50)
    print("审核小结")
    print("=" * 50)
    print(f"通过入库 : {len(approved)}")
    print(f"丢弃     : {discarded}")
    print(f"保留待审 : {len(remaining)}")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(run())
