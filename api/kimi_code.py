"""Async client for Kimi Code Search and Fetch endpoints."""

from __future__ import annotations

import asyncio
import platform
import random
import string
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

KIMI_CODE_USER_AGENT = "KimiCLI/1.30.0"
KIMI_CODE_VERSION = "1.30.0"
DEFAULT_SEARCH_URL = "https://api.kimi.com/coding/v1/search"
DEFAULT_FETCH_URL = "https://api.kimi.com/coding/v1/fetch"


@dataclass(slots=True)
class KimiSearchResult:
    site_name: str
    title: str
    url: str
    snippet: str
    content: str = ""
    date: str = ""


class KimiCodeError(RuntimeError):
    """Raised when Kimi Code returns an invalid or failed response."""


def create_tool_call_id(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{int(time.time() * 1000)}_{suffix}"


def build_msh_headers(api_key: str, tool_call_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": KIMI_CODE_USER_AGENT,
        "X-Msh-Tool-Call-Id": tool_call_id,
        "X-Msh-Platform": "kimi_cli",
        "X-Msh-Version": KIMI_CODE_VERSION,
        "X-Msh-Device-Name": "kimi-cli",
        "X-Msh-Device-Model": "kimi-cli",
        "X-Msh-Os-Version": platform.system().lower() or "unknown",
        "X-Msh-Device-Id": "kimi-cli",
    }


def normalize_limit(limit: int | None, fallback: int) -> int:
    try:
        value = int(limit if limit is not None else fallback)
    except (TypeError, ValueError):
        value = fallback
    return max(1, min(20, value))


def parse_search_results(data: Any) -> list[KimiSearchResult]:
    if not isinstance(data, dict):
        raise KimiCodeError("搜索服务返回格式无效")
    rows = data.get("search_results")
    if not isinstance(rows, list):
        raise KimiCodeError("搜索服务响应缺少 search_results")

    results: list[KimiSearchResult] = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise KimiCodeError(f"search_results[{index}] 格式无效")
        result = KimiSearchResult(
            site_name=str(item.get("site_name") or ""),
            title=str(item.get("title") or ""),
            url=str(item.get("url") or ""),
            snippet=str(item.get("snippet") or ""),
            content=item.get("content") if isinstance(item.get("content"), str) else "",
            date=item.get("date") if isinstance(item.get("date"), str) else "",
        )
        if result.title and result.url:
            results.append(result)
    return results


def format_search_results(
    results: list[KimiSearchResult],
    *,
    include_content: bool = False,
    max_content_chars: int = 4000,
) -> str:
    if not results:
        return "未找到相关搜索结果。"

    blocks: list[str] = []
    for index, result in enumerate(results, start=1):
        lines = [
            f"## {index}. {result.title}",
            f"Date: {result.date}" if result.date else "",
            f"Source: {result.site_name}" if result.site_name else "",
            f"URL: {result.url}",
            f"Summary: {result.snippet}" if result.snippet else "",
        ]
        if include_content and result.content:
            lines.extend(["", result.content[:max_content_chars]])
        blocks.append("\n".join(line for line in lines if line))
    return "\n\n---\n\n".join(blocks)


class KimiCodeClient:
    def __init__(
        self,
        *,
        api_key: str,
        search_url: str = DEFAULT_SEARCH_URL,
        fetch_url: str = DEFAULT_FETCH_URL,
        timeout_seconds: int = 30,
        proxy: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.search_url = search_url.strip() or DEFAULT_SEARCH_URL
        self.fetch_url = fetch_url.strip() or DEFAULT_FETCH_URL
        self.timeout_seconds = max(1, int(timeout_seconds or 30))
        self.proxy = proxy.strip() if proxy else None
        self.session = session

    async def search(
        self,
        *,
        query: str,
        limit: int,
        include_content: bool = False,
    ) -> list[KimiSearchResult]:
        if not self.api_key:
            raise KimiCodeError("Kimi Code API Key 未配置")
        body = {
            "text_query": query,
            "limit": normalize_limit(limit, limit),
            "enable_page_crawling": bool(include_content),
            "timeout_seconds": self.timeout_seconds,
        }
        data = await self._post_json(
            self.search_url,
            body,
            headers=build_msh_headers(self.api_key, create_tool_call_id("search")),
        )
        return parse_search_results(data)

    async def fetch(self, *, url: str) -> str:
        if not self.api_key:
            raise KimiCodeError("Kimi Code API Key 未配置")
        headers = build_msh_headers(self.api_key, create_tool_call_id("fetch"))
        headers["Accept"] = "text/markdown"
        return await self._post_text(self.fetch_url, {"url": url}, headers=headers)

    async def _post_json(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
        text = await self._post_text(url, body, headers=headers)
        try:
            import json

            return json.loads(text)
        except Exception as exc:
            raise KimiCodeError(f"搜索服务 JSON 解析失败: {exc}") from exc

    async def _post_text(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> str:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds + 5)
        session = self.session
        if session is None:
            async with aiohttp.ClientSession(timeout=timeout) as owned_session:
                return await self._request(owned_session, url, body, headers, timeout)
        return await self._request(session, url, body, headers, timeout)

    async def _request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout: aiohttp.ClientTimeout,
    ) -> str:
        try:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=timeout,
                proxy=self.proxy,
            ) as response:
                text = await response.text()
                if response.status < 200 or response.status >= 300:
                    detail = text.strip() or response.reason or "unknown error"
                    raise KimiCodeError(f"HTTP {response.status}: {detail}")
                return text
        except asyncio.TimeoutError as exc:
            raise KimiCodeError("Kimi Code 请求超时") from exc
        except aiohttp.ClientError as exc:
            raise KimiCodeError(f"Kimi Code 网络请求失败: {exc}") from exc

