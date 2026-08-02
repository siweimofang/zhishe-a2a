---
name: skill-param-extract
description: |
  装修参数提取。当用户咨询装修/量房/户型/面积/房间数/朝向/楼层时触发。
  通过 2 轮对话引导,提取用户房屋参数,生成结构化 JSON(用于 skill-quote / skill-layout)。
  适用:C 端业主自装咨询、需要先有参数再报价/布局的场景。
  不适用:已提供完整户型图(请用 skill-ocr-parse)。
triggerKeywords: [装修, 量房, 户型, 面积, 房间数, 朝向, 楼层, 新房, 老房, 几室几厅]
---

# 参数提取 Skill

## 知识层

### 装修参数结构
- 城市 / 区 / 面积 / 户型 / 朝向 / 楼层 / 装修方式 / 档次
- 房间列表:主卧/次卧/客厅/厨房/卫生间/阳台

### 反问顺序
1. 哪个城市 / 区?(沙箱实证 city_pricing.json 13 城)
2. 户型多大?(必填)
3. 半包 / 大包 / 全案?(必填)
4. 几室几厅?(必填)
5. 经济型 / 中档 / 中高档 / 豪华?(必填)

### 数据精度等级
- city_pricing.json:精度等级:沙箱实证
- 城市列表:精度等级:沙箱实证

## 能力层(2 个工具)

### 工具 1:`scripts/normalize.py`(5643 字节)
- **功能**:参数标准化(单位/格式/默认值)
- **输入**:原始用户输入(可能不规范)
- **输出**:结构化 JSON
- **gotcha**:中文数字需要转阿拉伯数字

### 工具 2:对话引导
- **功能**:2 轮对话强制收集必填项
- **轮次**:第 1 轮问城市/区 + 户型,第 2 轮问半包/大包 + 档次
- **gotcha**:缺一必问,不准默认

## 编排层

### 触发场景
- "我家要装修,90 平三室,半包,大概多少钱?"
- "想了解一下装修报价"
- "我房子在沈阳浑南,89 平"

### 输入
- 用户自然语言描述(自由文本)

### 输出 JSON Schema
```json
{
  "city": "沈阳",
  "district": "浑南",
  "total_area": 89,
  "room_count": "3室1厅",
  "rooms": [
    {"name": "主卧", "length": 3.5, "width": 3.2, "height": 2.8, "floor_type": "木地板", "wall_type": "乳胶漆"},
    {"name": "次卧", "length": 3.0, "width": 2.8, "height": 2.8, "floor_type": "木地板", "wall_type": "乳胶漆"},
    {"name": "客厅", "length": 4.5, "width": 3.8, "height": 2.8, "floor_type": "瓷砖", "wall_type": "乳胶漆"},
    {"name": "厨房", "length": 3.0, "width": 2.5, "height": 2.8, "floor_type": "瓷砖", "wall_type": "瓷砖"},
    {"name": "卫生间", "length": 2.5, "width": 2.0, "height": 2.8, "floor_type": "瓷砖", "wall_type": "瓷砖"},
    {"name": "阳台", "length": 3.0, "width": 1.5, "height": 2.8, "floor_type": "瓷砖", "wall_type": "乳胶漆"}
  ],
  "orientation": "南",
  "floor_number": 5,
  "decoration_age": "新房",
  "has_elevator": true,
  "package_type": "半包",
  "tier": "中档"
}
```

### Gotchas(2 条)
- 反问必须先问"哪个城市/区?" → 再问"户型多大?" → 再问"半包/大包?"
- 缺一必问,不准默认
- 必填项缺失必须返回反问,不准直接报价

## 协作层

### orchestrator C 端路径
```
skill-param-extract → skill-layout → skill-quote → skill-case-match
```

### orchestrator 入口
- 主入口:dispatch(user_intent) 自动选择路径
- 关键词:"我家""我房子""我家装修""我家要""装修多少钱""装修预算"
- C 端业主路径:extract → layout → quote → match

### 数据精度等级
- 城市列表:精度等级:沙箱实证(13 城 52 区)

### 上游
- 无(skill-param-extract 是 C 端入口)

### 下游
- skill-layout:布局规划
- skill-quote:报价计算

## 约束

- 反问必须先问"哪个城市/区?" → 再问"户型多大?" → 再问"半包/大包?"
- 缺一必问,不准默认
- 必填项缺失必须返回反问,不准直接报价
- 11 红线永久屏蔽(加微信/逼单/区域标签等)

## 免责声明

本 Skill 仅提供参数提取能力,不承诺任何具体装修结果。
所有参数需用户确认,实际价格以实地量房 + 业主预算为准。
本智能体不提供具体承诺价,建议实地量房 + 多家对比。

## 维护信息

- **owner**:agentd70403c6f6234856bdd73ecd3ec69226
- **company**:沈阳赫慕空间设计有限责任公司
- **legalRep**:马壮男
- **uscc**:91210105MA110C8544
- **lastUpdate**:2026-06-27
- **version**:1.0.0
