# Kimi 联网搜索 (astrbot_plugin_kimi_web_search)

使用 Kimi API 为 AstrBot 提供互联网搜索和网页正文获取能力。默认模式遵循 Kimi 官方文档，通过 Chat Completions 的 `builtin_function.$web_search` 实现联网搜索；也保留兼容模式，可配置为使用 Kimi CLI/coding endpoint。

## 功能

- `/kimi` 指令：直接搜索互联网
- `/kimifetch` 指令：读取指定网页正文
- LLM Tool `kimi_web_search`：让 AstrBot 在回答实时信息、新闻、文档、公告、论文等问题时自动搜索
- LLM Tool `kimi_web_fetch`：让 AstrBot 在需要阅读网页详情时自动抓取正文
- 可选 Skill：启用后安装 `kimi-web-search` Skill，并移除 LLM Tool

## 安装

在 AstrBot 插件管理中选择“从链接安装”，填入：

```text
https://github.com/Tsukumi233/astrbot_plugin_kimi_web_search
```

也可以克隆到 AstrBot 的插件目录：

```bash
cd AstrBot/data/plugins
git clone https://github.com/Tsukumi233/astrbot_plugin_kimi_web_search
```

## 配置

在插件配置页填写：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `api_mode` | `builtin_web_search` | `builtin_web_search` 使用官方 `$web_search`；`coding_endpoints` 使用 Kimi CLI/coding endpoint |
| `api_key` | 空 | Kimi API Key |
| `chat_base_url` | `https://api.moonshot.cn/v1` | 标准 Chat Completions base URL |
| `model` | `kimi-k2.6` | 支持 `$web_search` 的 Kimi 模型 |
| `search_url` | `https://api.kimi.com/coding/v1/search` | 仅 `coding_endpoints` 模式使用 |
| `fetch_url` | `https://api.kimi.com/coding/v1/fetch` | 仅 `coding_endpoints` 模式使用 |
| `user_agent` | 空 | 标准模式留空；coding endpoint 可填 `KimiCLI/1.30.0` |
| `default_limit` | `8` | coding endpoint 默认搜索结果数量，范围 1-20 |
| `include_content` | `false` | coding endpoint 搜索时是否抓取页面正文 |
| `enable_fetch` | `true` | 是否启用网页抓取工具 |
| `enable_skill` | `false` | 是否安装 Skill，并移除 LLM Tool |

## 使用

```text
/kimi Python 3.13 有什么新特性
/kimi 最新 AI 新闻
/kimifetch https://example.com/article
```

LLM Tool 会在 AstrBot 调用工具时自动使用：

- `kimi_web_search(query, limit, include_content)`
- `kimi_web_fetch(url)`

## 与 Kimi 官方文档的对应关系

默认 `builtin_web_search` 模式按官方文档实现：

- 请求 `chat.completions`
- 在 `tools` 中声明 `{"type":"builtin_function","function":{"name":"$web_search"}}`
- 工具调用返回后，将 `$web_search` 的 `arguments` 原样作为 `role=tool` 消息提交回模型
- 默认传入 `thinking: {"type": "disabled"}`，符合官方文档“使用 `$web_search` 时必须禁用思考能力”的说明

`coding_endpoints` 模式不是官方 `$web_search` 流程，而是兼容 Kimi CLI/coding endpoint 的实现，适合已有对应权限和 UA 需求的场景。

## 注意

- API Key 请只放在 AstrBot 插件配置中，不要提交到仓库。
- 标准 Kimi API 和 coding endpoint 的 base URL、model id、权限可能不同，请按实际账号能力配置。
- 插件使用 `aiohttp`，没有使用同步 `requests`。

## 许可

MIT License
