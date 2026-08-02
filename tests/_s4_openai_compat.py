"""
S4 验证:zhishe-a2a OpenAI 兼容端点是否真被外部 client 协议级兼容
- 用最朴素的 OpenAI SDK 调用方式(模拟腾讯元宝/智谱/豆包内部 client)
- 验证字段:HTTP 200 + choices[0].message.content + usage + model echo
"""
import urllib.request, json, time, os
from dotenv import load_dotenv
load_dotenv(r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\.env')
api_key = os.environ['A2A_API_KEY']

# 模拟第三方平台调用 zhishe-a2a(走永久 URL,模拟外部 client 真实场景)
url = 'https://tunnel.zhishe.top/v1/chat/completions'
body = json.dumps({
  'model': 'zhishe-a2a',
  'messages': [{'role': 'user', 'content': '简单一句话:你家能做全包吗?'}],
  'temperature': 0.3,
  'max_tokens': 500,
  'stream': False
}).encode('utf-8')
req = urllib.request.Request(url, data=body, headers={
  'Authorization': f'Bearer {api_key}',
  'Content-Type': 'application/json',
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'  # 浏览器 UA
}, method='POST')
t0 = time.time()
try:
  resp = urllib.request.urlopen(req, timeout=30)
  raw = resp.read().decode('utf-8')
  dt = round(time.time()-t0, 2)
  j = json.loads(raw)
  out = {
    's4_http': resp.status,
    's4_latency': dt,
    's4_object': j.get('object'),
    's4_model': j.get('model'),
    's4_choices_count': len(j.get('choices', [])),
    's4_first_choice_role': j['choices'][0]['message']['role'] if j.get('choices') else None,
    's4_first_choice_content_preview': j['choices'][0]['message']['content'][:120] if j.get('choices') else None,
    's4_finish_reason': j['choices'][0].get('finish_reason') if j.get('choices') else None,
    's4_usage_keys': list(j.get('usage', {}).keys()),
    's4_usage_total_tokens': j.get('usage', {}).get('total_tokens'),
    's4_protocol_compat_pass': all([
      resp.status == 200,
      j.get('object') == 'chat.completion',
      j.get('model') == 'zhishe-a2a',
      len(j.get('choices', [])) == 1,
      j['choices'][0].get('message', {}).get('role') == 'assistant',
      j['choices'][0].get('finish_reason') == 'stop',
      'prompt_tokens' in (j.get('usage') or {}),
      'completion_tokens' in (j.get('usage') or {}),
    ])
  }
  print(json.dumps(out, ensure_ascii=False, indent=2))
  import pathlib
  pathlib.Path(r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\s4_openai_compat.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
  print('SAVED: docs/s4_openai_compat.json')
except urllib.error.HTTPError as e:
  print(f'HTTP_ERR={e.code} | err={e.read().decode("utf-8", errors="replace")[:500]}')
