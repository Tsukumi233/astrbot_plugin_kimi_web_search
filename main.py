"""AstrBot plugin for Kimi web search."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

from .api.kimi_web import DEFAULT_FETCH_URL, DEFAULT_SEARCH_URL, KIMI_CODE_USER_AGENT, KimiWebClient, KimiWebError

try:
    from astrbot.core.provider.register import llm_tools as _llm_tools_registry
except ImportError:
    _llm_tools_registry = None


PLUGIN_NAME = "astrbot_plugin_kimi_web_search"
SKILL_NAME = "kimi-web-search"

CONFIG_PATHS = {
    "api_key": ("connection_settings", "api_key"),
    "search_url": ("connection_settings", "search_url"),
    "fetch_url": ("connection_settings", "fetch_url"),
    "timeout_seconds": ("connection_settings", "timeout_seconds"),
    "reuse_session": ("connection_settings", "reuse_session"),
    "proxy": ("connection_settings", "proxy"),
    "user_agent": ("connection_settings", "user_agent"),
    "default_limit": ("request_settings", "default_limit"),
    "include_content": ("request_settings", "include_content"),
    "max_content_chars": ("request_settings", "max_content_chars"),
    "enable_fetch": ("tool_settings", "enable_fetch"),
    "enable_skill": ("tool_settings", "enable_skill"),
}

CONFIG_DEFAULTS = {
    "api_key": "",
    "search_url": DEFAULT_SEARCH_URL,
    "fetch_url": DEFAULT_FETCH_URL,
    "timeout_seconds": 60,
    "reuse_session": False,
    "proxy": "",
    "user_agent": KIMI_CODE_USER_AGENT,
    "default_limit": 8,
    "include_content": False,
    "max_content_chars": 4000,
    "enable_fetch": True,
    "enable_skill": False,
}


class KimiWebSearchPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._session: aiohttp.ClientSession | None = None

    def _cfg(self, key: str, default=None):
        path = CONFIG_PATHS.get(key)
        if path:
            section = self.config.get(path[0], {})
            if isinstance(section, dict) and path[1] in section:
                return section[path[1]]
        return self.config.get(key, CONFIG_DEFAULTS.get(key, default))

    async def initialize(self):
        self._unregister_disabled_tools()
        if self._cfg("reuse_session", False):
            self._session = aiohttp.ClientSession()
        self._migrate_skill_to_persistent()
        if self._cfg("enable_skill", False):
            self._install_skill()
        else:
            self._uninstall_skill()
        if not self._cfg("api_key", ""):
            logger.warning(f"[{PLUGIN_NAME}] Kimi API Key 未配置")

    def _client(self) -> KimiWebClient:
        return KimiWebClient(
            api_key=str(self._cfg("api_key", "") or ""),
            search_url=str(self._cfg("search_url", DEFAULT_SEARCH_URL) or DEFAULT_SEARCH_URL),
            fetch_url=str(self._cfg("fetch_url", DEFAULT_FETCH_URL) or DEFAULT_FETCH_URL),
            timeout_seconds=int(self._cfg("timeout_seconds", 60) or 60),
            proxy=str(self._cfg("proxy", "") or "") or None,
            session=self._session,
            user_agent=str(self._cfg("user_agent", KIMI_CODE_USER_AGENT) or KIMI_CODE_USER_AGENT),
            default_limit=int(self._cfg("default_limit", 8) or 8),
            include_content=bool(self._cfg("include_content", False)),
            max_content_chars=int(self._cfg("max_content_chars", 4000) or 4000),
        )

    def _unregister_disabled_tools(self) -> None:
        if _llm_tools_registry is None:
            return
        if self._cfg("enable_skill", False):
            _llm_tools_registry.remove_func("kimi_web_search")
            _llm_tools_registry.remove_func("kimi_web_fetch")
            logger.info(f"[{PLUGIN_NAME}] Skill 已启用，已卸载 LLM Tool")
            return
        if not self._cfg("enable_fetch", True):
            _llm_tools_registry.remove_func("kimi_web_fetch")
            logger.info(f"[{PLUGIN_NAME}] Fetch 未启用，已卸载 kimi_web_fetch")

    async def _do_search(
        self,
        query: str,
        *,
        limit: int | None = None,
        include_content: bool | None = None,
    ) -> str:
        return await self._client().search(
            query=query,
            limit=limit,
            include_content=include_content,
        )

    async def _do_fetch(self, url: str) -> str:
        if not self._cfg("enable_fetch", True):
            return "Kimi 网页获取未启用。"
        content = await self._client().fetch_url_content(url=url)
        max_chars = max(1000, min(20000, int(self._cfg("max_content_chars", 4000) or 4000) * 3))
        return content[:max_chars]

    @filter.command("kimi")
    async def kimi_command(self, event: AstrMessageEvent, query: GreedyStr = ""):
        """使用 Kimi 搜索互联网。"""
        query = str(query or "").strip()
        if not query or query.lower() == "help":
            yield event.plain_result(
                "用法：/kimi Python 3.13 新特性\n"
                "配置：在插件设置中填写 Kimi API Key。"
            )
            return
        try:
            text = await self._do_search(query)
            yield event.plain_result(f"Kimi 搜索「{query}」结果：\n\n{text}")
        except KimiWebError as exc:
            logger.warning(f"[{PLUGIN_NAME}] /kimi 搜索失败: {exc}")
            yield event.plain_result(f"Kimi 搜索失败：{exc}")
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] /kimi 未预期错误: {exc}")
            yield event.plain_result(f"Kimi 搜索失败：{exc}")

    @filter.command("kimifetch")
    async def kimifetch_command(self, event: AstrMessageEvent, url: GreedyStr = ""):
        """使用 Kimi 获取网页正文。"""
        url = str(url or "").strip()
        if not url.startswith(("http://", "https://")):
            yield event.plain_result("用法：/kimifetch https://example.com/article")
            return
        try:
            text = await self._do_fetch(url)
            yield event.plain_result(f"Kimi 获取网页内容：\nURL: {url}\n\n{text}")
        except KimiWebError as exc:
            logger.warning(f"[{PLUGIN_NAME}] /kimifetch 失败: {exc}")
            yield event.plain_result(f"Kimi 获取网页失败：{exc}")
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] /kimifetch 未预期错误: {exc}")
            yield event.plain_result(f"Kimi 获取网页失败：{exc}")

    @filter.llm_tool(name="kimi_web_search")
    async def kimi_web_search_tool(
        self,
        event: AstrMessageEvent,
        query: str,
        limit: int = 0,
        include_content: bool = False,
    ) -> str:
        """使用 Kimi coding search 直连工具搜索互联网，适合查询最新新闻、文档、公告、博客、论文和网页信息。

        Args:
            query(string): 搜索关键词或问题，应当清晰、具体、自包含
            limit(number): 返回结果数量，1-20；传 0 使用插件默认值
            include_content(boolean): 是否同时抓取页面正文，会消耗更多上下文
        """
        del event
        if not query:
            return "错误：query 不能为空。"
        try:
            limit_value = None if int(limit or 0) <= 0 else int(limit)
            text = await self._do_search(
                query,
                limit=limit_value,
                include_content=include_content,
            )
            return f"Kimi 搜索「{query}」结果：\n\n{text}"
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] kimi_web_search tool failed: {exc}")
            return f"Kimi 搜索「{query}」失败：{exc}"

    @filter.llm_tool(name="kimi_web_fetch")
    async def kimi_web_fetch_tool(self, event: AstrMessageEvent, url: str) -> str:
        """使用 Kimi 获取指定 URL 的网页正文。

        Args:
            url(string): 要获取的网页完整 URL，必须是 HTTP/HTTPS 地址
        """
        del event
        if not url or not url.startswith(("http://", "https://")):
            return "错误：请提供完整的 HTTP/HTTPS URL。"
        try:
            text = await self._do_fetch(url)
            return f"Kimi 获取网页内容：\nURL: {url}\n\n{text}"
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] kimi_web_fetch tool failed: {exc}")
            return f"Kimi 获取网页「{url}」失败：{exc}"

    def _get_skill_manager(self):
        if hasattr(self, "_skill_mgr"):
            return self._skill_mgr
        try:
            from astrbot.core.skills import SkillManager

            self._skill_mgr = SkillManager()
        except ImportError:
            self._skill_mgr = None
        return self._skill_mgr

    def _get_plugin_data_path(self) -> Path:
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

            plugin_data_root = Path(get_astrbot_plugin_data_path())
        except ImportError:
            plugin_data_root = Path(__file__).parent.parent.parent / "plugin_data"
        plugin_data_dir = plugin_data_root / PLUGIN_NAME
        plugin_data_dir.mkdir(parents=True, exist_ok=True)
        return plugin_data_dir

    def _get_skill_persistent_path(self) -> Path:
        return self._get_plugin_data_path() / "skill"

    def _migrate_skill_to_persistent(self) -> None:
        source_dir = Path(__file__).parent / "skill"
        persistent_dir = self._get_skill_persistent_path()
        if source_dir.exists() and not persistent_dir.exists():
            try:
                shutil.copytree(source_dir, persistent_dir, symlinks=True)
                logger.info(f"[{PLUGIN_NAME}] Skill 已复制到持久化目录: {persistent_dir}")
            except Exception as exc:
                logger.error(f"[{PLUGIN_NAME}] Skill 复制失败: {exc}")

    def _install_skill(self) -> None:
        source_dir = self._get_skill_persistent_path()
        if not source_dir.exists() or source_dir.is_symlink():
            logger.error(f"[{PLUGIN_NAME}] Skill 源目录不可用: {source_dir}")
            return
        skill_mgr = self._get_skill_manager()
        if not skill_mgr:
            logger.error(f"[{PLUGIN_NAME}] SkillManager 不可用，无法安装 Skill")
            return
        tmp_zip: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_zip = Path(tmp.name)
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in source_dir.rglob("*"):
                    if file.is_file():
                        zf.write(file, f"{SKILL_NAME}/{file.relative_to(source_dir)}")
            skill_mgr.install_skill_from_zip(str(tmp_zip), overwrite=True)
            logger.info(f"[{PLUGIN_NAME}] Skill 已安装并激活")
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}] Skill 安装失败: {exc}")
        finally:
            if tmp_zip:
                tmp_zip.unlink(missing_ok=True)

    def _uninstall_skill(self) -> None:
        skill_mgr = self._get_skill_manager()
        if not skill_mgr:
            return
        try:
            skill_mgr.delete_skill(SKILL_NAME)
        except Exception:
            pass

    async def terminate(self):
        if self._session and not self._session.closed:
            await self._session.close()
