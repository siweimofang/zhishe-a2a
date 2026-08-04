# Layer-2 独立验证档案（2026-08-04）

知设知识库四层独立验证体系（Layer-1 规则引擎 → Layer-2 独立模型 → Layer-3 人工复核 → Layer-4 人工维护）第二层实施档案。

## 文件索引

| 文件 | 内容 |
| --- | --- |
| [01_adjudication_log_20260804.md](01_adjudication_log_20260804.md) | 驳回裁决记录：约 20 条验证器幻觉的逐条驳回理由 + 5 类系统性幻觉模式 |
| [02_fix_log_20260804.md](02_fix_log_20260804.md) | 修正日志：23 条数据修正（三轮）+ 3 条规则修正 + 验证器升级记录 + 备份清单 |
| [03_final_report_20260804.md](03_final_report_20260804.md) | 最终报告：66/66 通过、Layer-1 回归、测试与服务、体系级发现 |

## 一句话结论

66 条 standard 条目全部通过独立验证（28 条首轮即通过，38 条经三轮"验证器发现 → 人工裁决 → 修正 → 复验"闭环）；验证器发现 2 处 Layer-3 未覆盖的真实错误（表10.2.8 接缝高低差 0.5mm、石膏板≠人造木板），人工驳回约 20 处验证器幻觉，双向校验机制有效。

## 相关位置

- 数据：gotchas/data/v1.0/all_ku.json（66 条已写 metadata.verified_by）
- 规则：gotchas/data/v1.0/verification_rules.json（27 条，含 source 字段）
- 验证器：gotchas/pipeline/layer2_verify.py（背景知识 + 中文日志 + 代码块解析）
- 审计：gotchas/pipeline/validate_ku.py（Layer-1，回归全绿）
