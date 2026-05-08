# Changelog

## v0.4.0

- Change `kimi_web_fetch` to call `/coding/v1/fetch` directly.
- Add configurable `fetch_url`.

## v0.3.0

- Remove direct `/coding/v1/search` and `/coding/v1/fetch` endpoint mode.
- Use one OpenAI-compatible Chat Completions path for both standard Kimi API and coding plan.
- Keep configurable `base_url`, `model`, and `user_agent`.

## v0.2.0

- Rename user-facing feature to Kimi web search.
- Add official Kimi API `$web_search` mode through Chat Completions.
- Keep coding endpoint mode as an optional compatibility mode with configurable User-Agent.
- Rename LLM tools to `kimi_web_search` and `kimi_web_fetch`.

## v0.1.0

- Initial release.
- Add `/kimi` and `/kimifetch` commands.
- Add initial Kimi search and fetch LLM tools.
- Add optional Skill installation.
