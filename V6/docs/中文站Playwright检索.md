# 中文站 Playwright 站内搜索

## 目的

补全 **RSS / html_list** 对 SPA 中文财经站（如财联社）覆盖不足的问题：用真实浏览器打开各站**搜索页**（`search_url` + 三关键词），抽取稿件链接，并入 `run_once` Phase 0。

**不**用 Playwright 爬列表/首页/电报流（成本高）；财联社电报等仍可由 html_list/RSS 补位（`BROWSER_ZH_PRIMARY_MODE` 命中不足时自动回退）。

**仅中文站**（`config/browser_zh_sources.json`）；英文/外国站不走此路径。

## Cursor：Playwright MCP（交互调试）

项目已配置：

- 仓库：`.cursor/mcp.json`
- 用户级：`~/.cursor/mcp.json`（已追加 `playwright`）

重启 Cursor → **Settings → MCP**，确认 `playwright` 为绿色。可对 Agent 说：「用 Playwright 打开 cls.cn 搜索低空经济，列出 /detail/ 链接。」

官方说明：[Playwright MCP](https://playwright.dev/docs/getting-started-mcp)

## 流水线启用（scheduler / run-once）

```bash
cd V4
pip install playwright
playwright install chromium

# .env
BROWSER_ZH_SEARCH_ENABLED=true
BROWSER_ZH_MAX_AGE_HOURS=24
```

冒烟（只搜不入库）：

```bash
cd V4 && PYTHONPATH=. python scripts/run_browser_zh_search_once.py
```

完整链路仍走 `python -m src.main run-once`；浏览器结果与 RSS/html_list 合并后，继续 `filter_by_age`、抓正文、聚类。

**入库升级（V5）**：检索成功后，中文源建议同时开启 `ZH_INGEST_LLM_ENABLED=true`，走 [中文入库 LLM 流程](./中文入库LLM流程.md)（跳过 prefilter 关键词/字数门槛，抓正文后 LLM 门禁 + 聚类后事件提炼）。Playwright 只负责发现链接，不负责领域判题。

## 配置站点

编辑 `config/browser_zh_sources.json`：为每个 `source_id` 配置 **`search_url`**（`{query}` 占位）。Playwright 阶段**仅**按 `browser_zh_keywords.json` 打开搜索页，不配置 `list_url`。

站内搜索关键词（与 `search_keywords.json` 分离）见 **`config/browser_zh_keywords.json`**，当前为：`无人机`、`低空经济`、`eVTOL`。

## 与 MCP 的区别

| 方式 | 用途 |
|------|------|
| **Playwright MCP** | Cursor 里人工/Agent 调试、验收页面 |
| **`browser_zh_search.py`** | 定时任务自动跑，写入与 RSS 相同的 `SearchHit` 池 |
