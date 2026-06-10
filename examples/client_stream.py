"""A2A streaming client example.

Demonstrates how to consume Server-Sent Events (SSE) from
message/stream. The zhishe-a2a server returns text/event-stream chunks.

Usage:
    python examples/client_stream.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def stream_message(text: str, *, base_url: str = "http://127.0.0.1:8765") -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "stream-demo",
        "method": "message/stream",
        "params": {
            "message": {
                "role": "user",
                    "parts": [{"kind": "text", "text": text}],
            }
        },
    }
    print(f"Q: {text}\n")
    print("AGENT (streaming):")
    with httpx.stream(
        "POST",
        f"{base_url}/a2a/message/stream",
        json=payload,
        timeout=60.0,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    if "result" in obj and "parts" in obj["result"]:
                        for part in obj["result"]["parts"]:
                            if part.get("type") == "text":
                                print(part.get("text", ""), end="", flush=True)
                except json.JSONDecodeError:
                    pass
    print("\n[stream end]")


if __name__ == "__main__":
    stream_message("装修开工前需要准备什么?给一个清单")
