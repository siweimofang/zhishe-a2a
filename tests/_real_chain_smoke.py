"""
E2E 烟测 1:百炼开放平台 API 直接调 zhishe-a2a
(模拟"千问 APP 端用户问问题,百炼 LLM 是否真把请求路由到我们")
- 目的:验证百炼 → zhishe-a2a 这条链路是否真的能通
- 关键:百炼 LLM 是 Qwen-Plus,跟我们后端用的 DeepSeek-v4-pro 不是同一个 LLM
  - 如果百炼真的在用 Qwen-Plus 答用户问题(不路由到我们),那"知设 AI 装修顾问"在千问里就是百炼自己的 Qwen-Plus 答的,跟 zhishe-a2a 没关系
  - 如果百炼真的路由到我们,那响应里会带 V1.6 prompt 注入的内容特征(8公斤/30分钟/0.5兆欧...)
- 期望:真路由 → 答案含老法师细节 / 假路由 → 答案是百炼 Qwen-Plus 自答
"""
import urllib.request, json, time, os, sys
from dotenv import load_dotenv
load_dotenv(r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\.env')

# 直接打我们自己的端点(不绕 Cloudflare)
url = 'http://127.0.0.1:8765/v1/chat/completions'
api_key = os.environ['A2A_API_KEY']

# 模拟千问端用户问题
q = "我家90平装修,想知道半包大概多少钱?"

body = json.dumps({'model': 'xiaozhi', 'messages': [{'role': 'user', 'content': q}]}).encode('utf-8')
req = urllib.request.Request(url, data=body, headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}, method='POST')
t0 = time.time()
try:
  resp = urllib.request.urlopen(req, timeout=60)
  raw = resp.read().decode('utf-8')
  dt = round(time.time()-t0, 2)
  j = json.loads(raw)
  ans = j.get('choices', [{}])[0].get('message', {}).get('content', '')
  print(f'STATUS={resp.status} | {dt}s | chars={len(ans)}')
  print('---ANSWER---')
  print(ans)
  print('---END---')
  # 写文件
  out = {'q': q, 'elapsed': dt, 'status': resp.status, 'answer': ans, 'endpoint': 'localhost:8765'}
  import pathlib
  pathlib.Path(r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\real_chain_smoke.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
except urllib.error.HTTPError as e:
  print(f'HTTP_ERR={e.code} | err={e.read().decode("utf-8", errors="replace")[:500]}')
