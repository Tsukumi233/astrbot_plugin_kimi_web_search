"""Async clients for Kimi web search modes."""

from __future__ import annotations

import asyncio
import json
import platform
import random
import string
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

KIMI_CODE_USER_AGENT = "KimiCLI/1.30.0"
KIMI_CODE_VERSION = "1.30.0"
DEFAULT_CHAT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_CHAT_MODEL = "kimi-k2.6"
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
    """Raised when Kimi returns an invalid or failed response."""


def create_tool_call_id(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{int(time.time() * 1000)}_{suffix}"


def build_msh_headers(
    api_key: str,
    tool_call_id: str,
    *,
    user_agent: str = KIMI_CODE_USER_AGENT,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
        "X-Msh-Tool-Call-Id": tool_call_id,
        "X-Msh-Platform": "kimi_cli",
        "X-Msh-Version": KIMI_CODE_VERSION,
        "X-Msh-Device-Name": "kimi-cli",
        "X-Msh-Device-Model": "kimi-cli",
        "X-Msh-Os-Version": platform.system().lower() or "unknown",
        "X-Msh-Device-Id": "kimi-cli",
    }
    if not user_agent:
        headers.pop("User-Agent", None)
    return headers


def build_auth_headers(api_key: str, *, user_agent: str = "") -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


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
        chat_base_url: str = DEFAULT_CHAT_BASE_URL,
        model: str = DEFAULT_CHAT_MODEL,
        search_url: str = DEFAULT_SEARCH_URL,
        fetch_url: str = DEFAULT_FETCH_URL,
        timeout_seconds: int = 30,
        proxy: str | None = None,
        session: aiohttp.ClientSession | None = None,
        user_agent: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.6,
        disable_thinking: bool = True,
        max_rounds: int = 6,
    ) -> None:
        self.api_key = api_key.strip()
        self.chat_base_url = chat_base_url.strip().rstrip("/") or DEFAULT_CHAT_BASE_URL
        self.model = model.strip() or DEFAULT_CHAT_MODEL
        self.search_url = search_url.strip() or DEFAULT_SEARCH_URL
        self.fetch_url = fetch_url.strip() or DEFAULT_FETCH_URL
        self.timeout_seconds = max(1, int(timeout_seconds or 30))
        self.proxy = proxy.strip() if proxy else None
        self.session = session
        self.user_agent = user_agent.strip()
        self.max_tokens = max(1, int(max_tokens or 8192))
        self.temperature = float(temperature if temperature is not None else 0.6)
        self.disable_thinking = bool(disable_thinking)
        self.max_rounds = max(1, int(max_rounds or 6))

    async def builtin_web_search(self, *, query: str) -> str:
        """Run official Kimi `$web_search` through Chat Completions."""
        if not self.api_key:
            raise KimiCodeError("Kimi API Key 未配置")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "你是 Kimi。请基于联网搜索结果给出准确、简洁的回答，并保留关键来源。"},
            {"role": "user", "content": query},
        ]
        tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]
        last_content = ""

        for _ in range(self.max_rounds):
            body: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "tools": tools,
            }
            if self.disable_thinking:
                body["thinking"] = {"type": "disabled"}

            data = await self._post_json(
                self._chat_completions_url(),
                body,
                headers=build_auth_headers(self.api_key, user_agent=self.user_agent),
            )
            choice = self._first_choice(data)
            message = choice.get("message")
            if not isinstance(message, dict):
                raise KimiCodeError("Chat Completions 响应缺少 message")

            content = message.get("content")
            if isinstance(content, str):
                last_content = content

            finish_reason = choice.get("finish_reason")
            if finish_reason != "tool_calls":
                return last_content or "Kimi 未返回文本内容。"

            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list):
                raise KimiCodeError("Chat Completions 响应缺少 tool_calls")
            messages.append(self._assistant_tool_call_message(message))
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function")
                if not isinstance(function, dict):
                    continue
                name = str(function.get("name") or "")
                arguments = function.get("arguments") or "{}"
                if name != "$web_search":
                    tool_result: Any = f"Error: unable to find tool by name '{name}'"
                else:
                    tool_result = self._json_loads(arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

        raise KimiCodeError("Kimi web search 超过最大工具调用轮数")

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
            headers=build_msh_headers(
                self.api_key,
                create_tool_call_id("search"),
                user_agent=self.user_agent or KIMI_CODE_USER_AGENT,
            ),
        )
        return parse_search_results(data)

    async def fetch(self, *, url: str) -> str:
        if not self.api_key:
            raise KimiCodeError("Kimi Code API Key 未配置")
        headers = build_msh_headers(
            self.api_key,
            create_tool_call_id("fetch"),
            user_agent=self.user_agent or KIMI_CODE_USER_AGENT,
        )
        headers["Accept"] = "text/markdown"
        return await self._post_text(self.fetch_url, {"url": url}, headers=headers)

    def _chat_completions_url(self) -> str:
        if self.chat_base_url.endswith("/chat/completions"):
            return self.chat_base_url
        return f"{self.chat_base_url}/chat/completions"

    @staticmethod
    def _json_loads(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(str(raw or "{}"))
        except json.JSONDecodeError:
            return raw

    @staticmethod
    def _first_choice(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise KimiCodeError("Chat Completions 返回格式无效")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise KimiCodeError("Chat Completions 响应缺少 choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise KimiCodeError("Chat Completions choice 格式无效")
        return choice

    @staticmethod
    def _assistant_tool_call_message(message: dict[str, Any]) -> dict[str, Any]:
        result = {
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": message.get("tool_calls"),
        }
        reasoning_content = message.get("reasoning_content")
        if reasoning_content:
            result["reasoning_content"] = reasoning_content
        return result

    async def _post_json(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
        text = await self._post_text(url, body, headers=headers)
        try:
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
