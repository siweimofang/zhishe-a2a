#!/usr/bin/env python3
"""
标注流水线主入口：把经验素材批量转成候选 KU，落待审区。

用法：
    python run_annotate.py --input input/瓦工瓷砖.txt
    python run_annotate.py --input input/xx.txt --dry-run   # 只跑不写库
    python run_annotate.py --input input/xx.txt --resume    # 断点续跑

退出码：0=全部成功；1=有失败条目（见报告）；2=配置/环境错误。
"""
import argparse
import json
import sys
from pathlib import Path

# 让 annotator 包可被导入（本脚本位于 pipeline/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from annotator import config
from annotator import loader, extractor, validator, dedup, writer


def _load_checkpoint() -> dict:
    if config.CHECKPOINT_PATH.exists():
        try:
            return json.loads(config.CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_checkpoint(data: dict) -> None:
    config.CHECKPOINT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _clear_checkpoint() -> None:
    if config.CHECKPOINT_PATH.exists():
        config.CHECKPOINT_PATH.unlink()


def run(input_path: Path, dry_run: bool, resume: bool) -> int:
    # ── 配置检查 ──
    try:
        cfg = config.get_deepseek_config()
    except RuntimeError as e:
        print(f"[配置错误] {e}")
        return 2
    print(f"[配置] 模型={cfg['model']} base={cfg['base_url']} key={config.mask_key(cfg['api_key'])}")

    # ── 进料 ──
    try:
        material = loader.load_material(input_path)
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        return 2
    segments = material["segments"]
    print(f"[进料] 文件={input_path.name} 片段={len(segments)} 过短跳过={len(material['skipped_short'])}")
    if not segments:
        print("[结束] 无有效素材片段。")
        return 0

    # ── 断点 ──
    ckpt = _load_checkpoint() if resume else {}
    done_set = set(ckpt.get("done_segments", []))
    if resume and ckpt.get("input") == str(input_path):
        print(f"[续跑] 已完成片段 {sorted(done_set)}，从断点继续。")
    else:
        done_set = set()

    # ── 编号起点 ──
    existing_ids = validator.load_existing_ids()
    enums = validator.get_enums()
    existing_kus = dedup.load_existing_kus()
    id_counter = int(validator.next_ku_id(existing_ids).split("-")[-1])

    # ── 报告计数 ──
    report = {
        "segments_total": len(segments),
        "segments_done": 0,
        "candidates_extracted": 0,
        "valid": 0,
        "rejected": 0,
        "duplicates_flagged": 0,
        "extract_failed": 0,
        "rejections": [],
    }
    new_entries = []

    for idx, segment in enumerate(segments):
        if idx in done_set:
            report["segments_done"] += 1
            continue
        source = f"{input_path.name}#{idx + 1}"
        print(f"\n[片段 {idx + 1}/{len(segments)}] {segment[:30].replace(chr(10), ' ')}...")

        candidates, status = extractor.extract_candidates(segment, cfg)
        if status != "ok":
            report["extract_failed"] += 1
            report["rejections"].append(f"{source}: 抽取失败({status})")
            print(f"  × 抽取失败：{status}")
            done_set.add(idx)
            _save_checkpoint({"input": str(input_path), "done_segments": sorted(done_set)})
            continue

        report["candidates_extracted"] += len(candidates)

        # 校验；若出现 too_long，按 spec 决策重抽一次
        validated = _validate_batch(candidates, enums)
        if validated["has_too_long"]:
            print("  ↻ 发现超长字段，重抽一次...")
            candidates2, status2 = extractor.extract_candidates(segment, cfg)
            if status2 == "ok":
                validated = _validate_batch(candidates2, enums)

        for cand, errors in validated["results"]:
            if errors:
                report["rejected"] += 1
                report["rejections"].append(f"{source}: {'; '.join(errors)}")
                print(f"  × 打回：{'; '.join(errors)}")
                continue
            ku_id = f"GZ-SY-{id_counter:05d}"
            id_counter += 1
            ku = validator.enrich(cand, ku_id, source_file=source)
            hint = dedup.find_similar(ku, existing_kus)
            if hint:
                report["duplicates_flagged"] += 1
                print(f"  ⚠ {ku_id} 疑似重复 {hint['ku_id']}（{hint['reason']}）")
            else:
                print(f"  ✓ {ku_id} {ku.get('title', '')[:24]}")
            report["valid"] += 1
            new_entries.append(writer.make_entry(ku, hint, source))
            # 新入库的也加入比对池，避免批内自重复
            existing_kus.append(ku)

        report["segments_done"] += 1
        done_set.add(idx)
        _save_checkpoint({"input": str(input_path), "done_segments": sorted(done_set)})

    # ── 落盘 ──
    if dry_run:
        print("\n[dry-run] 不写入待审区。")
    else:
        total = writer.append_pending(new_entries)
        print(f"\n[落盘] 新增 {len(new_entries)} 条到待审区，当前待审总数 {total}。")

    _clear_checkpoint()
    _print_report(report, dry_run)
    return 1 if (report["extract_failed"] or report["rejected"]) else 0


def _validate_batch(candidates: list, enums) -> dict:
    """校验一批候选，返回 {results:[(cand, errors)], has_too_long:bool}。"""
    results = []
    has_too_long = False
    for cand in candidates:
        errors = validator.validate_candidate(cand, enums)
        if any(e.startswith("too_long") for e in errors):
            has_too_long = True
        results.append((cand, errors))
    return {"results": results, "has_too_long": has_too_long}


def _print_report(report: dict, dry_run: bool) -> None:
    print("\n" + "=" * 50)
    print("标注报告")
    print("=" * 50)
    print(f"素材片段总数      : {report['segments_total']}")
    print(f"已处理片段        : {report['segments_done']}")
    print(f"抽取候选总数      : {report['candidates_extracted']}")
    print(f"校验通过          : {report['valid']}")
    print(f"打回              : {report['rejected']}")
    print(f"疑似重复(已标记)  : {report['duplicates_flagged']}")
    print(f"抽取失败片段      : {report['extract_failed']}")
    if dry_run:
        print("模式              : dry-run（未写库）")
    if report["rejections"]:
        print("\n打回/失败明细：")
        for r in report["rejections"]:
            print(f"  - {r}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="知设 Gotchas 标注流水线")
    parser.add_argument("--input", required=True, help="素材文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只抽取校验，不写待审区")
    parser.add_argument("--resume", action="store_true", help="从断点续跑")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        # 相对路径默认相对 pipeline/input/
        candidate = config.INPUT_DIR / args.input
        if candidate.exists():
            input_path = candidate
    sys.exit(run(input_path, args.dry_run, args.resume))


if __name__ == "__main__":
    main()
