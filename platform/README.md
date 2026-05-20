# platform — 情报前端

Next.js 实现的 Event Intelligence 工作台，与 `V3/src/bff` 对接。项目背景与验收路径见仓库根目录 [README.md](../README.md)。

## 技术栈

Next.js（App Router）、TypeScript、Tailwind CSS、React Query、Zustand、Recharts、Framer Motion。

## 页面

| 路由 | 功能 |
|------|------|
| `/` | 指标 Dashboard |
| `/events` | 事件列表与筛选 |
| `/events/[id]` | 通稿、时间线、溯源、QA（核心页） |
| `/qa` | 通稿质量复核 |
| `/search` | 已入库事件检索 |
| `/settings` | 数据源、关键词、定时任务配置 |

## 本地运行

```bash
npm install
npm run dev
```

连接后端：在 `.env.local` 设置 `BFF_BASE_URL=http://127.0.0.1:8787`（先启动 `V3` 的 `run-bff`）。未配置时自动使用 `lib/mock/`。

**演示采集**：顶栏或 Dashboard 点击「开始采集搜索」，会后台执行 V3 `run-once` 并显示「开始进行搜索了…」；完成后刷新事件列表即可看到新入库数据。

```bash
npm run build   # 生产构建（--webpack）
```
