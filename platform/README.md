# AI 低空经济情报平台（前端）

Event-first 情报展示 UI，技术栈：Next.js 15+、TypeScript、Tailwind、React Query、Zustand、Recharts、Framer Motion。

## 启动

```bash
cd platform
npm install
npm run dev
```

浏览器打开 http://localhost:3000

## 连接 V3 真实数据（可选）

终端 1 — BFF（读取 `V3/data/events.json`）：

```bash
cd V3
pip install fastapi uvicorn
PYTHONPATH=. python -m src.main run-bff
```

终端 2 — 前端：

```bash
cd platform
echo 'BFF_BASE_URL=http://127.0.0.1:8787' >> .env.local
npm run dev
```

BFF 不可达时，Route Handlers 自动回退到 `lib/mock/events.ts`。

## 页面

| 路径 | 说明 |
|------|------|
| `/` | Dashboard |
| `/events` | 事件列表 |
| `/events/[id]` | **Event Detail**（核心：通稿 + 溯源 + QA） |
| `/qa` | QA 审核 |
| `/search` | 事件搜索 |
