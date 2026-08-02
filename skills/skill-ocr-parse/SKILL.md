# OCR 户型图解析 Skill

## 触发条件
当用户上传户型图 / 扫描图纸 / CAD 图识别时触发

## 目标
从户型图(JPG/PNG/PDF)中提取房间布局,生成结构化 JSON(供 skill-quote / skill-layout 使用)

## 输入
- 户型图文件(JPG/PNG/PDF)
- 简单文本描述(备用)

## 输出
- 房间列表(name/length/width)
- 户型类型(几室几厅)
- 置信度(0-1)

## Gotchas
→ 见 gotchas.md

## 脚本
- `scripts/ocr_client.py`:OCR 调用(占位,Phase 4 接真实 API)
- `scripts/parse_floor_plan.py`:文本→结构化 JSON

## 约束
- 置信度 < 0.7 必须人工确认
- 房间数 < 2 报错
