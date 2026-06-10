"""A2A basic client example.

Demonstrates how to send a message to the zhishe-a2a server using
JSON-RPC 2.0 over HTTP, per the A2A 0.2.5 protocol.

Usage:
    python examples/client_basic.py
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import httpx

# Ensure project root is on sys.path so 'app.*' imports work when running
# this file directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def send_message(text: str, *, base_url: str = "http://127.0.0.1:8765") -> dict:
    """Send a single text message via A2A message/send (JSON-RPC 2.0)."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                    "parts": [{"kind": "text", "text": text}],
            }
        },
    }
    resp = httpx.post(f"{base_url}/a2a/message/send", json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    question = "沈阳 90 平毛坯房,基础装修大概多少钱?"
    print(f"Q: {question}\n")
    result = send_message(question)
    print("RAW RESPONSE:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Try to extract the agent's text reply (best-effort, A2A shape).
    try:
        parts = result["result"]["parts"]
        text = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
        print("\nAGENT REPLY:")
        print(text)
    except (KeyError, TypeError):
        pass


if __name__ == "__main__":
    main()
