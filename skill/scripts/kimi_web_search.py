#!/usr/bin/env python3
"""Standalone Kimi web search skill script."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k2.6"
DEFAULT_FETCH_URL = "https://api.kimi.com/coding/v1/fetch"
KIMI_CODE_USER_AGENT = "KimiCLI/1.30.0"
PLUGIN_NAME = "astrbot_plugin_kimi_web_search"


def _find_astrbot_data_path() -> str:
    current = os.path.dirname(__file__)
    for _ in range(6):
        parent = os.path.dirname(current)
        if os.path.basename(parent) == "data" and os.path.isdir(os.path.join(parent, "config")):
            return parent
        if os.path.basename(current) == "skills" and os.path.isdir(os.path.join(parent, "config")):
            return parent
        current = parent
    return os.environ.get("ASTRBOT_DATA_PATH", "").strip()


def _load_plugin_config() -> dict[str, Any]:
    data_path = _find_astrbot_data_path()
    if not data_path:
        return {}
    config_path = os.path.join(data_path, "config", f"{PLUGIN_NAME}_config.json")
    if not os.path.exists(config_path):
        config_path = os.path.join(data_path, "config", f"{PLUGIN_NAME}.json")
    try:
        with open(config_path, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {}
    for key, value in raw.items():
        result[key] = value.get("value") if isinstance(value, dict) and "value" in value else value
    return result


def _cfg(config: dict[str, Any], section: str, key: str, default: Any) -> Any:
    value = config.get(section)
    if isinstance(value, dict) and key in value:
        return value[key]
    return config.get(key, default)


def _headers(api_key: str, user_agent: str = "") -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def _fetch_headers(api_key: str, user_agent: str = KIMI_CODE_USER_AGENT) -> dict[str, str]:
    headers = _headers(api_key, user_agent)
    headers["Accept"] = "text/markdown"
    return headers


def _chat_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _post(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int) -> str:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc


def _web_search(
    *,
    api_key: str,
    query: str,
    base_url: str,
    model: str,
    timeout: int,
    user_agent: str = "",
    max_rounds: int = 6,
) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "你是 Kimi。请基于联网搜索结果给出准确、简洁的回答，并保留关键来源。"},
        {"role": "user", "content": query},
    ]
    tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]
    last_content = ""
    for _ in range(max_rounds):
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": 8192,
            "temperature": 0.6,
            "thinking": {"type": "disabled"},
            "tools": tools,
        }
        raw = _post(_chat_url(base_url), body, _headers(api_key, user_agent), timeout)
        data = json.loads(raw)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise SystemExit("Chat Completions 响应缺少 choices")
        choice = choices[0]
        message = choice.get("message") or {}
        if isinstance(message.get("content"), str):
            last_content = message["content"]
        if choice.get("finish_reason") != "tool_calls":
            return last_content or "Kimi 未返回文本内容。"

        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            raise SystemExit("Chat Completions 响应缺少 tool_calls")
        assistant_message = {
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": tool_calls,
        }
        if message.get("reasoning_content"):
            assistant_message["reasoning_content"] = message["reasoning_content"]
        messages.append(assistant_message)
        for tool_call in tool_calls:
            function = tool_call.get("function") if isinstance(tool_call, dict) else {}
            name = function.get("name") if isinstance(function, dict) else ""
            arguments = function.get("arguments", "{}") if isinstance(function, dict) else "{}"
            try:
                tool_result = json.loads(arguments)
            except json.JSONDecodeError:
                tool_result = arguments
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "name": name,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )
    raise SystemExit("Kimi web search 超过最大工具调用轮数")


def main() -> int:
    parser = argparse.ArgumentParser(description="Kimi web search skill")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--url", required=True)
    args = parser.parse_args()

    config = _load_plugin_config()
    api_key = (
        os.environ.get("KIMI_API_KEY", "").strip()
        or os.environ.get("KIMI_CODE_API_KEY", "").strip()
        or str(_cfg(config, "connection_settings", "api_key", "") or "").strip()
    )
    if not api_key:
        raise SystemExit("Kimi API Key 未配置")

    timeout = int(_cfg(config, "connection_settings", "timeout_seconds", 60) or 60)
    base_url = (
        os.environ.get("KIMI_BASE_URL")
        or os.environ.get("KIMI_CHAT_BASE_URL")
        or _cfg(config, "connection_settings", "base_url", DEFAULT_BASE_URL)
    )
    model = os.environ.get("KIMI_MODEL") or _cfg(
        config, "connection_settings", "model", DEFAULT_MODEL
    )
    fetch_url = os.environ.get("KIMI_FETCH_URL") or _cfg(
        config, "connection_settings", "fetch_url", DEFAULT_FETCH_URL
    )
    user_agent = str(_cfg(config, "connection_settings", "user_agent", "") or "")

    if args.command == "fetch":
        print(
            _post(
                fetch_url,
                {"url": args.url},
                _fetch_headers(api_key, user_agent or KIMI_CODE_USER_AGENT),
                timeout,
            )
        )
        return 0

    print(
        _web_search(
            api_key=api_key,
            query=args.query,
            base_url=base_url,
            model=model,
            timeout=timeout,
            user_agent=user_agent,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
