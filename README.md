# 低空经济 Event Intelligence Platform — V5

**生产轨**：多源采集 → 事件聚类 → 扩搜 → AI 通稿 → QA → 微信公众号草稿箱 + 情报工作台。

| 组件 | 目录 | 端口 |
|------|------|------|
| 流水线 + BFF | `V5/` | `:8787` |
| 前端 | `platform/` | `:3000` |
| 事件扩搜（阶段三） | `event_enhancement/` | — |

完整说明：[V5/docs/PRD.md](V5/docs/PRD.md) · [V5/README.md](V5/README.md)

## 克隆

```bash
git clone -b V5 git@github.com:Czou-hahaha/wechat_auto_pipeline_project.git
cd wechat_auto_pipeline_project
```

## 快速启动

**后端**

```bash
cd V5
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt fastapi uvicorn
cp .env.example .env   # 填入 DEEPSEEK_API_KEY、微信等
cp data/demo/*.json data/
PYTHONPATH=. python -m src.main run-bff
```

**前端**

```bash
cd platform
npm install
printf 'BFF_BASE_URL=http://127.0.0.1:8787\n' > .env.local
npm run dev
```

浏览器打开 http://localhost:3000

## 测试

```bash
cd V5 && PYTHONPATH=. python -m pytest tests/ -q
```

## 仓库结构

```
├── V5/                  # 主流水线 + BFF + 文档
├── platform/            # Next.js 情报前端
└── event_enhancement/   # 事件扩搜子系统
```

勿将 `.env` 或 API Key 提交至仓库。
