# V3 测试说明

## 目录

| 路径 | 用途 |
|------|------|
| `tests/test_*.py` | `pytest` 单元测试（无网络依赖为主） |
| `tests/integration/` | 需联网或可写大文件的**集成 CLI**（`run_*.py`） |
| `tests/data/search/` | 检索/去重报告等**可重复生成**的 JSON、Markdown |
| `tests/data/fixtures/` | 固定 URL 列表等**手工维护**的输入 |
| `tests/data/dedupe_runs/*/` | `run_embedding_urls_ingest.py` 的测试落库目录 |
| `tests/data/event_enhancement_runs/` | `run_event_enhancement_fixture.py` 默认工作目录（可写，勿提交敏感数据） |

生产环境入库仍使用项目根下 **`DATA_DIR`（默认 `./data`）** 的 `articles.json` / `events.json`，与 `tests/data` 分离。

## 历史聚类 fixture → 阶段三（事件增强）

不跑检索、不跑 `run_once`，仅用 **`tests/data/dedupe_runs/beijing`**（或 `--fixture-dir`）下的三份 JSON，复制到可写目录后补齐成员稿、刷新事件时间窗，再调用与生产相同的 ``run_event_enhancement_post_pipeline``。

```bash
export EVENT_ENHANCEMENT_DATABASE_URL=
# 或删除该行：JSON 模式，GDELT+向量结果写入 <work-dir>/event_enhancement_last_run.json
python tests/integration/run_event_enhancement_fixture.py
```

说明见脚本顶部 docstring。``EVENT_ENHANCEMENT_DATABASE_URL`` 留空时走 **JSON 模式**（无须 PostgreSQL），结果在 ``<work-dir>/event_enhancement_last_run.json``。hydrate 单测见 ``tests/test_event_enhancement_hydrate.py``。**口径说明**见 ``docs/事件增强测试与容量说明.md``。

## 模块一 → 模块二（检索 → 去重/聚类报告）

在 **`V3/` 目录**下执行（请先 `cd` 到本仓库的 `V3/`，相对路径如 `tests/data/...` 才正确）：

```bash
python tests/integration/run_search_flow.py
python tests/integration/verify_search_dedupe_chain.py
python tests/integration/run_saved_search_dedupe_report.py
```

契约：`run_search_flow` 写出 `tests/data/search/test_search_results.json`（对象数组，每条含 `url`、`title`、`snippet`、`published_at`、`from_rss` 等）；`run_saved_search_dedupe_report` 读取同结构并拉全文、跑向量聚类，写出 `tests/data/search/dedupe_report_from_saved_search.json` 及 `*_阅读摘要.md`。

## 其它 CLI

```bash
python tests/integration/run_fetch_embed_dedupe.py --max-fetch 20
python tests/integration/run_embedding_urls_ingest.py \
  --input tests/data/fixtures/trump_xi_summit_dedupe_test_input.json \
  --data-dir tests/data/dedupe_runs/trump_xi
```
