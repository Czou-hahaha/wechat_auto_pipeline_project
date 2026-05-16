# V3 — 低空经济 Event Intelligence 流水线

V3 是 [wechat_auto_pipeline_project](https://github.com/Czou-hahaha/wechat_auto_pipeline_project) 的 **Event 情报版**：从多源检索 → 事件聚类 → AI 通稿 → QA →（可选）公众号草稿。

## 模块一览

| 阶段 | 模块 | 说明 |
|------|------|------|
| 检索 | `search.py` / `rss_aggregate.py` / `gdelt_search.py` | RSS + GDELT + 栏目页 |
| 入库聚类 | `pipeline.py` / `ingest_cluster.py` | 去重、向量/主题聚类 → `events.json` |
| 阶段三 | `event_enhancement_workflow.py` | 事件扩搜（`event_enhancement/`） |
| 阶段四 | `services/ai_press_writer/` | 多稿 → `event_press_zh` |
| 阶段五 | `services/qa_rewrite/` | 通稿 QA + 条件重写 |
| 配置 | `config/data_sources.json` / `search_keywords.json` | 数据源与关键词 |
| BFF | `src/bff/` | 供前端 `platform/` 读取 |
| 演示数据 | `data/demo/` | 可提交 Git 的 fixture |

流程图见 `docs/`：`检索模块流程图.md`、`入库与事件聚类流程.md`、`AI事件通稿生成模块流程.md`、`AI通稿质量控制模块流程.md`。

## 快速开始

```bash
cd V3
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY 等

# 演示：用仓库内 demo 数据 + BFF + 前端（无需跑检索）
cp data/demo/*.json data/
PYTHONPATH=. python -m src.main run-bff

# 全链路单次（需 API Key + 网络）
PYTHONPATH=. python -m src.main run-once

# 定时（.env 中 SCHEDULE_ENABLED=true）
PYTHONPATH=. python -m src.main run-scheduler
```

## CLI

| 命令 | 作用 |
|------|------|
| `run-once` | 检索 → 聚类 → 摘要/通稿 → 可选微信草稿 |
| `run-scheduler` | 按 `SCHEDULE_MORNING/EVENING_HOUR` 定时 run-once |
| `run-bff` | FastAPI `:8787`，供前端读取事件与配置 |
| `generate-event-press` | 仅对已有事件生成通稿 |
| `push-today-drafts` | 将当日摘要推入公众号草稿箱 |

## 测试

```bash
PYTHONPATH=. python -m pytest tests/ -q
```

集成脚本见 `tests/README.md`。
