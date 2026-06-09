# V5 中文 LLM 入库 — run-once 验收（2026-06-07）

**命令**：`BROWSER_ZH_SEARCH_ENABLED=true ZH_INGEST_LLM_ENABLED=true ZH_SKIP_LENGTH_GATE=true python -m src.main run-once`  
**日志**：`data/run_once_zh_llm_20260607T080943Z.log`  
**耗时**：~7.6 min · exit 0

## 对比旧链路（20260607T071509Z）

| 指标 | 旧（无 ZH_INGEST_LLM） | 新（ZH LLM 路径） |
|------|------------------------|-------------------|
| skipped_prefilter | **11** | **0** |
| skipped_too_short | 0 | **0** |
| candidates 进入抓正文 | 12 | **15** |
| skipped_policy（含 LLM 门禁） | 0 | **14** |
| 本批新簇/通稿 | 0 | 0 |

## 结论

1. **prefilter 绕过生效**：财联社/第一财经链接不再在抓正文前被关键词误杀。
2. **字数门槛跳过生效**：`skipped_too_short=0`。
3. **LLM 单篇门禁生效**：14 条在抓正文后被 DeepSeek 拒绝（如公司股份增持、韩国政治任命、财联社政治敏感电报等），日志含 `skip zh LLM article gate`。
4. **本批 14h 窗内无低空主稿入库**：LLM 过滤后 `prepared_buffer` 为空 → `clusters overview: none`；属数据窗口内容问题，非流程故障。

## 启用方式（持久化）

在 `V5/.env` 写入：

```env
BROWSER_ZH_SEARCH_ENABLED=true
ZH_INGEST_LLM_ENABLED=true
ZH_SKIP_LENGTH_GATE=true
```

## 测试

```bash
PYTHONPATH=. python -m pytest tests/test_zh_article_gate.py tests/test_zh_event_extract.py tests/test_zh_ingest_gate.py -q
# 11 passed
```
