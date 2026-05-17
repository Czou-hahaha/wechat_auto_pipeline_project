# V3 — 后端流水线

Event Intelligence 的采集、聚类、通稿、QA 与 BFF 实现。总览与复现步骤见仓库根目录 [README.md](../README.md)。

## 流水线阶段

| 阶段 | 入口 | 输出 |
|------|------|------|
| 检索 | `pipeline.run_once` | 候选文章 |
| 聚类 | `ingest_cluster` / topic 聚类 | `events.json`、`articles.json` |
| 扩搜 | `event_enhancement_workflow` | 增补关联稿 |
| 通稿 | `event_press_workflow` | `event_press_zh` |
| QA | `services/qa_rewrite` | `event_press_qa_*` 字段 |

流程图：`docs/检索模块流程图.md`、`docs/入库与事件聚类流程.md`、`docs/AI事件通稿生成模块流程.md`、`docs/AI通稿质量控制模块流程.md`。

## CLI

```bash
export PYTHONPATH=.
python -m src.main run-once          # 全链路
python -m src.main run-scheduler   # 定时（SCHEDULE_*）
python -m src.main run-bff         # API :8787
python -m src.main generate-event-press
```

## 配置

- `config/data_sources.json` — 站点与抓取方式（RSS / html_list）
- `config/search_keywords.json` — 中英检索词与分类词
- `.env` — API Key、调度、阈值（见 `.env.example`）

## Demo 数据

`data/demo/`：可提交仓库的完整事件样本，用于 BFF/前端验收。说明见 `data/demo/README.md`。

## 测试

```bash
PYTHONPATH=. python -m pytest tests/ -q
```
