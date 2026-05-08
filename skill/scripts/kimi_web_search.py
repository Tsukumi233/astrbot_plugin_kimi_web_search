#!/usr/bin/env python3
"""Standalone Kimi coding search/fetch skill script."""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import string
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_SEARCH_URL = "https://api.kimi.com/coding/v1/search"
DEFAULT_FETCH_URL = "https://api.kimi.com/coding/v1/fetch"
KIMI_CODE_USER_AGENT = "KimiCLI/1.30.0"
KIMI_CODE_VERSION = "1.30.0"
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


def _tool_call_id(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{int(time.time() * 1000)}_{suffix}"


def _headers(api_key: str, prefix: str, user_agent: str = KIMI_CODE_USER_AGENT, accept: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": user_agent or KIMI_CODE_USER_AGENT,
        "X-Msh-Tool-Call-Id": _tool_call_id(prefix),
        "X-Msh-Platform": "kimi_cli",
        "X-Msh-Version": KIMI_CODE_VERSION,
        "X-Msh-Device-Name": "kimi-cli",
        "X-Msh-Device-Model": "kimi-cli",
        "X-Msh-Os-Version": platform.system().lower() or "unknown",
        "X-Msh-Device-Id": "kimi-cli",
    }
    if accept:
        headers["Accept"] = accept
    return headers


def _post(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int) -> str:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 5) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc


def _format_results(data: dict[str, Any], include_content: bool) -> str:
    rows = data.get("search_results")
    if not isinstance(rows, list):
        raise SystemExit("搜索服务响应缺少 search_results")
    blocks: list[str] = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        lines = [
            f"## {index}. {item.get('title') or ''}",
            f"Date: {item.get('date')}" if item.get("date") else "",
            f"Source: {item.get('site_name')}" if item.get("site_name") else "",
            f"URL: {item.get('url') or ''}",
            f"Summary: {item.get('snippet') or ''}",
        ]
        if include_content and item.get("content"):
            lines.extend(["", str(item["content"])[:4000]])
        blocks.append("\n".join(line for line in lines if line))
    return "\n\n---\n\n".join(blocks) if blocks else "未找到相关搜索结果。"


def main() -> int:
    parser = argparse.ArgumentParser(description="Kimi coding search/fetch skill")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=0)
    search.add_argument("--include-content", action="store_true")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--url", required=True)
    args = parser.parse_args()

    config = _load_plugin_config()
    api_key = (
        os.environ.get("KIMI_CODE_API_KEY", "").strip()
        or os.environ.get("KIMI_API_KEY", "").strip()
        or str(_cfg(config, "connection_settings", "api_key", "") or "").strip()
    )
    if not api_key:
        raise SystemExit("Kimi coding plan API Key 未配置")

    timeout = int(_cfg(config, "connection_settings", "timeout_seconds", 60) or 60)
    user_agent = str(_cfg(config, "connection_settings", "user_agent", KIMI_CODE_USER_AGENT) or KIMI_CODE_USER_AGENT)

    if args.command == "fetch":
        fetch_url = os.environ.get("KIMI_FETCH_URL") or _cfg(
            config, "connection_settings", "fetch_url", DEFAULT_FETCH_URL
        )
        print(
            _post(
                fetch_url,
                {"url": args.url},
                _headers(api_key, "fetch", user_agent=user_agent, accept="text/markdown"),
                timeout,
            )
        )
        return 0

    search_url = os.environ.get("KIMI_SEARCH_URL") or _cfg(
        config, "connection_settings", "search_url", DEFAULT_SEARCH_URL
    )
    default_limit = int(_cfg(config, "request_settings", "default_limit", 8) or 8)
    limit = max(1, min(20, int(args.limit or default_limit)))
    body = {
        "text_query": args.query,
        "limit": limit,
        "enable_page_crawling": bool(args.include_content),
        "timeout_seconds": timeout,
    }
    text = _post(search_url, body, _headers(api_key, "search", user_agent=user_agent), timeout)
    print(_format_results(json.loads(text), args.include_content))
    return 0


if __name__ == "__main__":
    sys.exit(main())
