# 低空经济 Event Intelligence Platform — V6

**开发轨（已封板）**：在 V5 全链路之上增加统一事件图谱、反馈→Prompt 闭环、数据源健康通知、流水线阶段指标等。

| 组件 | 目录 | 端口 |
|------|------|------|
| 流水线 + BFF | `V6/` | `:8788` |
| 前端 | `platform-v6/` | `:3001` |
| 事件扩搜（阶段三） | `event_enhancement/` | — |

完整说明：[V6/docs/PRD.md](V6/docs/PRD.md) · [V6/README.md](V6/README.md)

## 克隆

```bash
git clone -b V6 git@github.com:Czou-hahaha/wechat_auto_pipeline_project.git
cd wechat_auto_pipeline_project
```

## 快速启动

```bash
cd platform-v6
npm install
npm run dev   # 自动启动 ../V6 BFF :8788，再开 Next
```

浏览器打开 http://localhost:3001

**全链路（实验，需配置 `V6/.env`）**

```bash
cd V6
cp .env.example .env
PYTHONPATH=. python -m src.main run-once
```

## 测试

```bash
cd V6 && PYTHONPATH=. python -m pytest tests/ -q
```

## 仓库结构

```
├── V6/                  # 主流水线 + BFF + 文档
├── platform-v6/         # Next.js 情报前端
└── event_enhancement/   # 事件扩搜子系统
```

勿将 `.env` 或 API Key 提交至仓库。
