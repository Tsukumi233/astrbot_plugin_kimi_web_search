# Kimi Code Search

Use this skill when you need fresh web search results or page content through Kimi Code Plan.

## Commands

Search the web:

```bash
python scripts/kimi_code_search.py search --query "Python 3.13 new features" --limit 8
```

Fetch a page:

```bash
python scripts/kimi_code_search.py fetch --url "https://example.com/article"
```

The script reads configuration from AstrBot plugin config when available. You can also set:

- `KIMI_CODE_API_KEY`
- `KIMI_SEARCH_URL`
- `KIMI_FETCH_URL`

