# V5 — MVP 闭环版本（事件地图 + 记忆 + 自动补源 + 反馈迭代）

V5 基于 V4 的可运行主链路构建，目标是形成一个可演示、可迭代的最小闭环：

- 检索与聚类
- 事件增强与通稿生成
- QA 重写
- 发布与标记
- 用户反馈回流
- 自动补充候选数据源
- 事件地图与最小记忆快照

## 流水线阶段

| 阶段 | 入口 | 输出 |
|------|------|------|
| 检索 | `pipeline.run_once` | 候选文章 |
| 聚类 | `ingest_cluster` / topic 聚类 | `events.json`、`articles.json` |
| 扩搜 | `event_enhancement_workflow` | 增补关联稿 |
| 通稿 | `event_press_workflow` | `event_press_zh` |
| QA | `services/qa_rewrite` | `event_press_qa_*` 字段 |
| 事件地图（MVP） | `services/event_map_mvp` | event-level nodes/edges/evidence |
| 事件记忆（MVP） | `services/event_memory_mvp` | `data/event_memory_snapshots.json` |
| 自动补源（MVP） | `services/source_discovery_mvp` | `data/source_candidates.json` |
| 反馈回流（MVP） | `services/feedback_loop_mvp` | `data/feedback_events.json` |

流程图：`docs/检索模块流程图.md`、`docs/入库与事件聚类流程.md`、`docs/AI事件通稿生成模块流程.md`、`docs/AI通稿质量控制模块流程.md`。

`run_once` 仍保留 V4 阶段三/四/五能力；V5 在 BFF 增加了 MVP 闭环接口（见下文）。

## CLI

```bash
export PYTHONPATH=.
python -m src.main run-once          # 全链路（含可选图记忆）
python -m src.main run-scheduler   # 定时（SCHEDULE_*）
python -m src.main run-bff         # API :8787
python -m src.main generate-event-press

# 图记忆演示 / 初始化 PG
python scripts/run_event_memory_demo.py
python scripts/init_event_graph_db.py
```

## MVP API（V5 新增）

- `GET /api/events/{event_id}/map`：返回事件地图（节点/边/证据）
- `POST /api/events/{event_id}/memory/refresh`：刷新事件记忆快照
- `GET /api/events/{event_id}/memory`：读取事件记忆快照
- `POST /api/feedback`：写入用户反馈（stage/category/note）
- `GET /api/feedback/summary`：反馈聚合统计
- `POST /api/sources/discover`：从当前文章自动发现候选来源域名
- `GET /api/sources/candidates`：查看候选来源
- `POST /api/sources/candidates/{host}/probe`：自动探测 RSS/html_list 可用性

## 配置

- `config/data_sources.json` — 站点与抓取方式（RSS / html_list）
- `config/search_keywords.json` — 中英检索词与分类词
- `config/event_graph.json` — 演化阈值、NER、关系模式（V4）
- `.env` — API Key、调度、阈值（见 `.env.example`，含 `EVENT_GRAPH_*`）
- `data/feedback_events.json` — 用户反馈
- `data/source_candidates.json` — 候选数据源及探测状态
- `data/event_memory_snapshots.json` — 事件记忆快照

## Demo 数据

`data/demo/`：可提交仓库的完整事件样本，用于 BFF/前端验收。说明见 `data/demo/README.md`。

## 文档

- **产品 PRD（V5 能力 + V6 方向）**：[`docs/PRD.md`](docs/PRD.md)
- 流程与验收：见 PRD §11 文档索引

## 测试

```bash
PYTHONPATH=. python -m pytest tests/ -q
PYTHONPATH=. python scripts/platform_frontend_e2e.py --skip-mutations
```
