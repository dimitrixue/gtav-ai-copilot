"""Streaming client for the DeepSeek-compatible chat completions endpoint."""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Iterator


API_URL = "https://api.deepseek.com/chat/completions"
PARATERA_BASE_URL = "https://llmapi.paratera.com"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def stream_multimodal(prompt: str, context: dict, screenshot_base64: str) -> Iterator[str]:
    api_key = os.environ.get("PARATERA_API_KEY", "").strip()
    if api_key:
        base_url = os.environ.get("PARATERA_BASE_URL", PARATERA_BASE_URL).strip().rstrip("/")
        if base_url != PARATERA_BASE_URL:
            raise RuntimeError("PARATERA_BASE_URL 必须为 https://llmapi.paratera.com")
        url = base_url + "/v1/chat/completions"
        model = os.environ.get("PARATERA_MODEL", "").strip()
        if not model:
            raise RuntimeError("请在 .env 中配置支持图片输入的 PARATERA_MODEL")
        open_request = urllib.request.build_opener(_NoRedirect()).open
    else:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key or api_key == "your_key_here":
            raise RuntimeError("请在 .env 中配置 DEEPSEEK_API_KEY 或 PARATERA_API_KEY")
        url = API_URL
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
        open_request = urllib.request.urlopen
    payload = {
        "model": model,
        "stream": True,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt + "\n\nTelemetry and tactical context:\n" + json.dumps(context, ensure_ascii=False)},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + screenshot_base64}},
        ]}],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with open_request(request, timeout=90) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                event = json.loads(chunk)
                if event.get("error"):
                    detail = str(event["error"]).replace(api_key, "[已隐藏]")
                    raise RuntimeError(f"模型 API 返回错误：{detail[:500]}")
                content = event.get("choices", [{}])[0].get("delta", {}).get("content", "")
            except (json.JSONDecodeError, IndexError, AttributeError):
                continue
            if isinstance(content, str) and content:
                yield content
