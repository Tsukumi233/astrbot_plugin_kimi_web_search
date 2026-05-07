# Kimi Code 搜索 (astrbot_plugin_kimi_code_search)

使用 Kimi Code Plan 的 Search / Fetch 服务为 AstrBot 提供互联网搜索和网页正文获取能力。实现参考了 AstrBot Star 插件结构和本地 MeowSev 的 Kimi Code 请求头与接口格式。

## 功能

- `/kimi` 指令：直接搜索互联网
- `/kimifetch` 指令：读取指定网页正文
- LLM Tool `kimi_code_search`：让 AstrBot 在回答实时信息、新闻、文档、公告、论文等问题时自动搜索
- LLM Tool `kimi_code_fetch`：让 AstrBot 在需要阅读网页详情时自动抓取正文
- 可选 Skill：启用后安装 `kimi-code-search` Skill，并移除 LLM Tool

## 安装

在 AstrBot 插件管理中选择“从链接安装”，填入：

```text
https://github.com/Tsukumi233/astrbot_plugin_kimi_code_search
```

也可以克隆到 AstrBot 的插件目录：

```bash
cd AstrBot/data/plugins
git clone https://github.com/Tsukumi233/astrbot_plugin_kimi_code_search
```

## 配置

在插件配置页填写：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `api_key` | 空 | Kimi Code Plan API Key |
| `search_url` | `https://api.kimi.com/coding/v1/search` | Search endpoint |
| `fetch_url` | `https://api.kimi.com/coding/v1/fetch` | Fetch endpoint |
| `default_limit` | `8` | 默认搜索结果数量，范围 1-20 |
| `include_content` | `false` | 搜索时是否抓取页面正文 |
| `enable_fetch` | `true` | 是否启用网页抓取工具 |
| `enable_skill` | `false` | 是否安装 Skill，并移除 LLM Tool |

## 使用

```text
/kimi Python 3.13 有什么新特性
/kimi 最新 AI 新闻
/kimifetch https://example.com/article
```

LLM Tool 会在 AstrBot 调用工具时自动使用：

- `kimi_code_search(query, limit, include_content)`
- `kimi_code_fetch(url)`

## 注意

- API Key 请只放在 AstrBot 插件配置中，不要提交到仓库。
- Kimi Code Search / Fetch endpoint 属于 Kimi Code Plan 能力，使用前请确认你的账号权限。
- 插件使用 `aiohttp`，没有使用同步 `requests`。

## 许可

MIT License

