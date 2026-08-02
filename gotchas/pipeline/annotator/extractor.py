"""
抽取层：调 DeepSeek，把经验片段转成候选 KU（未校验）。

零第三方依赖，用标准库 urllib。失败重试 + 指数退避。
"""
import json
import re
import time
import urllib.request
import urllib.error
from typing import List, Tuple

from . import config
from . import prompts


def _call_deepseek(system_prompt: str, user_prompt: str, cfg: dict) -> str:
    """单次调用，返回模型文本内容。失败抛异常。"""
    url = f"{cfg['base_url']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    obj = json.loads(body)
    return obj["choices"][0]["message"]["content"]


def _extract_json_array(text: str) -> List[dict]:
    """从模型输出里稳健地解析出 JSON 数组（容忍代码块包裹/前后多余文字）。"""
    text = text.strip()
    # 去掉可能的 ```json ... ``` 包裹
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # 直接尝试
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
    except json.JSONDecodeError:
        pass
    # 退而求其次：截取第一个 [ 到最后一个 ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end + 1]
        obj = json.loads(snippet)  # 仍失败则抛异常，由上层记为抽取失败
        if isinstance(obj, list):
            return obj
    raise ValueError("模型输出无法解析为 JSON 数组")


def extract_candidates(segment: str, cfg: dict = None) -> Tuple[List[dict], str]:
    """
    对单个经验片段抽取候选 KU。

    返回 (候选列表, 状态)。状态为 "ok" 或 "failed:原因"。
    失败时已按 EXTRACT_MAX_RETRY 重试。
    """
    if cfg is None:
        cfg = config.get_deepseek_config()

    user_prompt = prompts.build_user_prompt(segment)
    last_err = ""
    for attempt in range(config.EXTRACT_MAX_RETRY + 1):
        try:
            content = _call_deepseek(prompts.SYSTEM_PROMPT, user_prompt, cfg)
            candidates = _extract_json_array(content)
            return candidates, "ok"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            # 429/5xx 退避重试
            if e.code in (429, 500, 502, 503, 504) and attempt < config.EXTRACT_MAX_RETRY:
                time.sleep(2 ** attempt)
                continue
            break
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = f"网络/超时: {e}"
            if attempt < config.EXTRACT_MAX_RETRY:
                time.sleep(2 ** attempt)
                continue
            break
        except (json.JSONDecodeError, ValueError, KeyError, IndexError) as e:
            last_err = f"解析失败: {e}"
            if attempt < config.EXTRACT_MAX_RETRY:
                time.sleep(1)
                continue
            break
    return [], f"failed:{last_err}"
