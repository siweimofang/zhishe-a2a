# -*- coding: utf-8 -*-
"""知识库投喂入库脚本：备份 -> 校验 -> 合并进 data/knowledge.json

用法:
    python feeds/scripts/feed_merge.py            # 合并 03_待入库条目/ 下所有 json
    python feeds/scripts/feed_merge.py --dry-run  # 只预览，不改文件

条目格式(与 knowledge.json 一致):
    {"id": "k101", "category": "分类", "tags": ["标签"], "question": "问题", "answer": "答案"}
每个待入库文件可以是单条对象或对象数组。
"""
import argparse
import io
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # feeds/
KNOWLEDGE = os.path.normpath(os.path.join(BASE, os.pardir, "data", "knowledge.json"))
PENDING_DIR = os.path.join(BASE, "03_待入库条目")
BACKUP_DIR = os.path.join(BASE, "scripts", "backup")

ID_RE = re.compile(r"^k\d{3,}$")
REQUIRED = ("id", "category", "tags", "question", "answer")


def load_json(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, data):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def validate(item, idx, errors):
    for field in REQUIRED:
        if field not in item or item[field] in (None, ""):
            errors.append("条目%d缺少必填字段: %s" % (idx, field))
            return
    if not ID_RE.match(str(item["id"])):
        errors.append("条目%d的id格式错误: %s (应为k+3位以上数字)" % (idx, item["id"]))
    if not isinstance(item["tags"], list) or not item["tags"]:
        errors.append("条目%d的tags必须是非空数组" % idx)
    if not isinstance(item["question"], str) or len(item["question"]) < 5:
        errors.append("条目%d的question过短" % idx)
    if not isinstance(item["answer"], str) or len(item["answer"]) < 20:
        errors.append("条目%d的answer过短" % idx)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只预览不写文件")
    args = parser.parse_args()

    if not os.path.isdir(PENDING_DIR):
        print("待入库目录不存在: %s" % PENDING_DIR)
        sys.exit(1)

    pending_files = sorted(f for f in os.listdir(PENDING_DIR) if f.endswith(".json"))
    if not pending_files:
        print("没有待入库条目（03_待入库条目/ 下无 json 文件）")
        return

    existing = load_json(KNOWLEDGE)
    existing_ids = {str(it["id"]) for it in existing}
    new_items, errors, skipped = [], [], []

    for fname in pending_files:
        fpath = os.path.join(PENDING_DIR, fname)
        try:
            data = load_json(fpath)
        except Exception as e:
            errors.append("%s: 解析失败 %s" % (fname, e))
            continue
        items = data if isinstance(data, list) else [data]
        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                errors.append("%s: 第%d条不是对象" % (fname, i))
                continue
            before = len(errors)
            validate(item, i, errors)
            if len(errors) > before:
                continue
            if str(item["id"]) in existing_ids:
                skipped.append("%s(与现有条目id冲突)" % item["id"])
                continue
            if any(str(x["id"]) == str(item["id"]) for x in new_items):
                skipped.append("%s(本批内重复)" % item["id"])
                continue
            new_items.append(item)

    print("现有知识库: %d 条" % len(existing))
    print("待入库文件: %d 个, 新增条目: %d 条" % (len(pending_files), len(new_items)))
    if skipped:
        print("跳过(冲突/重复): %s" % ", ".join(skipped))
    if errors:
        print("校验失败, 未合并:")
        for e in errors:
            print("  - %s" % e)
        sys.exit(1)
    if not new_items:
        print("没有可入库的新条目")
        return
    if args.dry_run:
        print("DRY-RUN: 未写入文件")
        return

    if not os.path.isdir(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(BACKUP_DIR, "knowledge_%s.json" % stamp)
    dump_json(backup, existing)
    print("已备份: %s" % backup)

    merged = existing + new_items
    dump_json(KNOWLEDGE, merged)
    print("合并完成: %d -> %d 条 (新增 %d)" % (len(existing), len(merged), len(new_items)))


if __name__ == "__main__":
    main()
