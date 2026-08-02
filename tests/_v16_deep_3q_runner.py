import urllib.request, urllib.error, json, time, os
from dotenv import load_dotenv
load_dotenv(r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\.env')
api_key = os.environ['A2A_API_KEY']
url = 'http://127.0.0.1:8765/v1/chat/completions'
qs = [
  ('Q1_水电价格验收', '我家90平水电改造,工长说要1.8万,按25米开槽算的,这价格合理吗?怎么验收不让他糊弄我?'),
  ('Q2_材料真假', '装修公司给我用的伟星水管和雨虹防水,怎么分辨真假?乳胶漆也想确认是不是正品。'),
  ('Q3_施工顺序', '我家施工队现在在做水电,下一步是什么?我能看出他做得对不对吗?如果错了会有什么后果?'),
]
results = []
for name, q in qs:
  body = json.dumps({'model': 'xiaozhi', 'messages': [{'role': 'user', 'content': q}]}).encode('utf-8')
  req = urllib.request.Request(url, data=body, headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}, method='POST')
  t0 = time.time()
  try:
    resp = urllib.request.urlopen(req, timeout=60)
    raw = resp.read().decode('utf-8')
    dt = round(time.time()-t0, 2)
    j = json.loads(raw)
    ans = j.get('choices', [{}])[0].get('message', {}).get('content', '')
    print(f'=== {name} | HTTP {resp.status} | {dt}s | chars={len(ans)} ===')
    print(ans)
    print()
    results.append({'name': name, 'q': q, 'elapsed': dt, 'status': resp.status, 'answer': ans})
  except urllib.error.HTTPError as e:
    dt = round(time.time()-t0, 2)
    raw = e.read().decode('utf-8', errors='replace')
    print(f'=== {name} | HTTP {e.code} | {dt}s | err ===')
    print(raw[:2000])
    results.append({'name': name, 'q': q, 'elapsed': dt, 'status': e.code, 'error': raw[:2000]})
import pathlib
pathlib.Path(r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\v16_deep_3q_report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print('SAVED: docs/v16_deep_3q_report.json')
