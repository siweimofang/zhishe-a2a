# -*- coding: utf-8 -*-
import json
import csv

# 读 knowledge.json
with open(r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\data\knowledge.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 输出 CSV(腾讯元器知识库问答对格式)
# 列:问题,答案,分类,标签
out_path = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\data\knowledge_yuanqi_import.csv'
with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['问题', '答案', '分类', '标签'])
    for k in data:
        writer.writerow([
            k['question'],
            k['answer'],
            k['category'],
            ','.join(k['tags'])
        ])

print(f'CSV 生成完成: {out_path}')
print(f'共 {len(data)} 条知识')

# 同时生成 JSON 备份(供其他平台用)
out_json = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\data\knowledge_yuanqi_import.json'
with open(out_json, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f'JSON 备份: {out_json}')
