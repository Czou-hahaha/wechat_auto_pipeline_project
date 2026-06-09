# 事件增强（Event Enhancement）

低空经济情报：**最近 48h 内事件**按 `importance_score` 排序取 **Top3**，经 **GDELT（12h）** 扩搜 → 正文抽取（trafilatura）→ **BAAI/bge-m3** 向量 → **FAISS 余弦 > 0.8** 过滤后写入 PostgreSQL。

## 与 V3 `run_once` 的衔接（**必选**）

在 V3 运行目录配置 **`EVENT_ENHANCEMENT_DATABASE_URL`**（`postgresql+asyncpg://...`）并完成 **[数据库迁移](alembic/versions/)**（含 `002_align_v3_fields`）后，每次 [`V3/src/pipeline.py`](../V3/src/pipeline.py) 的 `run_once` 会在 JSON 落库后**自动**执行 [`V3/src/event_enhancement_workflow.py`](../V3/src/event_enhancement_workflow.py)（JSON→PG→扩搜→回写）。未配置或依赖缺失时 **整轮 run_once 失败**。表与 JSON 字段对应见 [`V3/docs/数据库结构_事件增强.md`](../V3/docs/数据库结构_事件增强.md)。

本目录 CLI 仍可用于单独联调 PG 与 GDELT。

## 环境

- Python **3.11+**
- Docker（PostgreSQL 16，默认映射本机 **5433**）

## 快速开始

```bash
cd event_enhancement
cp .env.example .env
docker compose up -d
```

将 `.env` 中 `DATABASE_URL` 与端口对齐（与 `docker-compose.yml` 一致）。

完成 **Alembic 迁移**（至少到 `002_align_v3_fields`，与 V3 JSON 字段对齐）：

```bash
export PYTHONPATH="$PWD"
export DATABASE_URL="postgresql://event_enh:event_enh@127.0.0.1:5433/event_enhancement"
alembic upgrade head
```

日常运行 CLI 仍使用 `.env` 里的 **`postgresql+asyncpg://...`**。

```bash
export PYTHONPATH="$PWD"
python -m event_enhancement.cli seed-demo
python -m event_enhancement.cli scan
python -m event_enhancement.cli expand-batch
```

## 配置

- [config/expansion.yaml](config/expansion.yaml)：`important_hosts`、`keywords`、`anchor_terms`、GDELT 限速/退避、`similarity_threshold`、`expansion_ranking_window_hours`（默认 48）等。

## 模块说明

| 路径 | 作用 |
|------|------|
| `event_enhancement/scoring/importance.py` | importance 四项 |
| `event_enhancement/gdelt/client.py` | 429 指数退避、UA 轮换、并发与最小间隔 |
| `event_enhancement/pipeline/expansion.py` | 刷新分数、选 TopN、扩搜入库 |

## 注意

- 首次本地向量会下载 **BAAI/bge-m3** 权重。
- `expand-batch` 会请求 **GDELT** 与候选 **HTTP 落地页**，请在合规网络环境下运行。
