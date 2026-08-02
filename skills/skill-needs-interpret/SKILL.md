# 需求解读 Skill

## 触发条件
当设计师查看客户需求/线索分析/客户意向解读时触发

## 目标
基于 skill-talk-analysis 输出,生成空间分析 + 报价预判 + 沟通建议

## 输入
- 客户画像(来自 skill-talk-analysis)
- 风险清单
- 原始谈单文本

## 输出
- 空间分析(户型推荐/拆改建议)
- 报价预判(基于 city_pricing.json)
- 沟通建议(应对高/中/低风险)

## Gotchas
→ 见 gotchas.md

## 脚本
- `scripts/needs_analyze.py`:需求分析(基于画像 + 风险)
