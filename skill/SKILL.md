# Kimi Web Search

Use this skill when you need fresh web search results or page content through Kimi.

## Commands

Search the web:

```bash
python scripts/kimi_web_search.py search --query "Python 3.13 new features"
```

Fetch a page:

```bash
python scripts/kimi_web_search.py fetch --url "https://example.com/article"
```

The script reads configuration from AstrBot plugin config when available. You can also set:

- `KIMI_API_KEY`
- `KIMI_CODE_API_KEY`
- `KIMI_BASE_URL`
- `KIMI_CHAT_BASE_URL`
- `KIMI_MODEL`
