"""Async OpenAI-compatible client for Kimi web search."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k2.6"
DEFAULT_FETCH_URL = "https://api.kimi.com/coding/v1/fetch"
KIMI_CODE_USER_AGENT = "KimiCLI/1.30.0"


class KimiWebError(RuntimeError):
    """Raised when Kimi returns an invalid or failed response."""


def build_headers(api_key: str, *, user_agent: str = "") -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def build_fetch_headers(api_key: str, *, user_agent: str = KIMI_CODE_USER_AGENT) -> dict[str, str]:
    headers = build_headers(api_key, user_agent=user_agent)
    headers["Accept"] = "text/markdown"
    return headers


class KimiWebClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        fetch_url: str = DEFAULT_FETCH_URL,
        timeout_seconds: int = 60,
        proxy: str | None = None,
        session: aiohttp.ClientSession | None = None,
        user_agent: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.6,
        disable_thinking: bool = True,
        max_rounds: int = 6,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/") or DEFAULT_BASE_URL
        self.model = model.strip() or DEFAULT_MODEL
        self.fetch_url = fetch_url.strip() or DEFAULT_FETCH_URL
        self.timeout_seconds = max(1, int(timeout_seconds or 60))
        self.proxy = proxy.strip() if proxy else None
        self.session = session
        self.user_agent = user_agent.strip()
        self.max_tokens = max(1, int(max_tokens or 8192))
        self.temperature = float(temperature if temperature is not None else 0.6)
        self.disable_thinking = bool(disable_thinking)
        self.max_rounds = max(1, int(max_rounds or 6))

    async def web_search(self, *, query: str) -> str:
        """Run Kimi `$web_search` through OpenAI-compatible Chat Completions."""
        if not self.api_key:
            raise KimiWebError("Kimi API Key 未配置")

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
                headers=build_headers(self.api_key, user_agent=self.user_agent),
            )
            choice = self._first_choice(data)
            message = choice.get("message")
            if not isinstance(message, dict):
                raise KimiWebError("Chat Completions 响应缺少 message")

            content = message.get("content")
            if isinstance(content, str):
                last_content = content

            if choice.get("finish_reason") != "tool_calls":
                return last_content or "Kimi 未返回文本内容。"

            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list):
                raise KimiWebError("Chat Completions 响应缺少 tool_calls")
            messages.append(self._assistant_tool_call_message(message))
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function")
                if not isinstance(function, dict):
                    continue
                name = str(function.get("name") or "")
                arguments = function.get("arguments") or "{}"
                if name == "$web_search":
                    tool_result: Any = self._json_loads(arguments)
                else:
                    tool_result = f"Error: unable to find tool by name '{name}'"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

        raise KimiWebError("Kimi web search 超过最大工具调用轮数")

    async def fetch_url_content(self, *, url: str) -> str:
        """Fetch a URL through the Kimi coding fetch endpoint."""
        if not self.api_key:
            raise KimiWebError("Kimi API Key 未配置")
        return await self._post_text(
            self.fetch_url,
            {"url": url},
            headers=build_fetch_headers(
                self.api_key,
                user_agent=self.user_agent or KIMI_CODE_USER_AGENT,
            ),
        )

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    async def _post_json(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
        text = await self._post_text(url, body, headers=headers)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise KimiWebError(f"Chat Completions JSON 解析失败: {exc}") from exc

    async def _post_text(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> str:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
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
                    raise KimiWebError(f"HTTP {response.status}: {detail}")
                return text
        except asyncio.TimeoutError as exc:
            raise KimiWebError("Kimi 请求超时") from exc
        except aiohttp.ClientError as exc:
            raise KimiWebError(f"Kimi 网络请求失败: {exc}") from exc

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
            raise KimiWebError("Chat Completions 返回格式无效")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise KimiWebError("Chat Completions 响应缺少 choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise KimiWebError("Chat Completions choice 格式无效")
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
