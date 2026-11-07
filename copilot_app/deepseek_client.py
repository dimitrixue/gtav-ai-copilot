"""Streaming client for the DeepSeek-compatible chat completions endpoint."""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Iterator


API_URL = "https://api.deepseek.com/chat/completions"


def stream_multimodal(prompt: str, context: dict, screenshot_base64: str) -> Iterator[str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    payload = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash",
        "stream": True,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt + "\n\nTelemetry and tactical context:\n" + json.dumps(context, ensure_ascii=False)},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + screenshot_base64}},
        ]}],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                content = json.loads(chunk).get("choices", [{}])[0].get("delta", {}).get("content", "")
            except (json.JSONDecodeError, IndexError, AttributeError):
                continue
            if isinstance(content, str) and content:
                yield content
