# V6 — 已封板（归档）

> **2026-06-09 起 V6 封板**：不再修改代码/配置/文档。活跃开发请使用 **`V7/` + `platform-v7/`**（BFF `:8789`、前端 `:3001`）。

---

V6 从 V5 复制可运行全链路，与 **V5 生产轨并行**：

| 轨道 | 目录 | BFF | 前端 |
|------|------|-----|------|
| **生产 / 每日采集** | `V5/` + `platform/` | `:8787` | `:3000` |
| **V6 开发** | `V6/` + `platform-v6/` | `:8788` | `:3001` |

**历史封板规则（已移交 V7）**：V5 仅 hotfix；V6 已冻结；新功能在 `V7/` + `platform-v7/`。

**定时采集**：仅 **V5** 跑 `run-scheduler`（8:00 / 20:00）。V6 默认 `BFF_SCHEDULER_AUTOSTART=false`，BFF 启动不会拉起调度进程。

## 快速启动

```bash
# 推荐：一条命令拉起 BFF :8788 + 前端 :3001
cd platform-v6
npm install
npm run dev   # 脚本会自动启动 ../V6 BFF，再开 Next

# 仅后端（调试 API）
cd V6 && ./scripts/start_bff_v6.sh

# 全链路（实验 data，不影响 V5）
cd V6 && PYTHONPATH=. python -m src.main run-once
```

## V6 新增能力

### 统一事件图谱
- `GET /api/events/{id}/graph` — 合并 Event Graph + 地图 + 记忆 + 历史链
- 详情页 **「事件图谱」** Tab：迷你关系图 + 时间轴 + 关联事件 + 记忆摘要

### 反馈 → Prompt Engineering
- `FeedbackPromptEngine`：反馈 category → `hard_rules` / `soft_rules` 建议
- `POST /api/feedback/prompt/recompute|apply|rollback`
- 前端 **`/feedback`**：汇总 + diff 预览 + 人工确认 apply

### 数据源接入向导
- `POST /api/sources/intake/probe|save` — RSS / html_list / browser_zh 三分法探测
- 设置页 **接入向导**：填 URL → 探测 → 一键保存

### 健康通知
- `GET /api/notifications` — 聚合数据源健康告警
- Dashboard / 顶栏 badge + 设置页「编辑 URL」修复闭环

### 流水线指标
- `run_once` 写入 `data/phase_timings_last_run.json`
- Dashboard 展示各阶段耗时条形图

### 扩搜质量（共享 event_enhancement）
- 英文 GDELT query 默认 **12 词** + 特殊字符清洗，降低 429/illegal character

## 测试

```bash
cd V6
PYTHONPATH=. python -m pytest tests/ -q
PLATFORM_BASE=http://127.0.0.1:3001 BFF_BASE=http://127.0.0.1:8788 \
  PYTHONPATH=. python scripts/platform_frontend_e2e.py --skip-mutations
```

## 文档

- [`docs/PRD.md`](docs/PRD.md) — V6 产品需求、验收标准与 **V7 路线图**
- [`docs/数据源接入规范.md`](docs/数据源接入规范.md) — 三种 ingest 模式
- V5 流程文档仍适用：`docs/检索模块流程图.md` 等

## CLI

与 V5 相同，额外：

```bash
# 重建 Event Graph 快照（首次迁移 events.json 后建议跑一次）
PYTHONPATH=. python -c "
from src.config import Settings
from src.storage import JsonStore
from src.services.event_intelligence_graph.service import rebuild_graph_from_store
rebuild_graph_from_store(JsonStore(Settings().data_path()))
"
```
