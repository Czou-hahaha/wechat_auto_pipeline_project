# platform-v6 — V6 前端

连接 **V6 BFF `:8788`**，与生产 `platform/` (`:3000` → `:8787`) 并行。

## 启动

```bash
cp .env.example .env.local   # BFF_BASE_URL=http://127.0.0.1:8788
npm install
npm run dev   # 自动启动 V6 BFF :8788 + Next :3001
```

仅前端（需另开终端已跑 BFF）：`npm run dev:next`

## V6 页面

| 路径 | 说明 |
|------|------|
| `/dashboard` | 指标 + 健康告警 + run-once 阶段耗时 |
| `/events/{id}` | 通稿 / **事件图谱** Tab |
| `/feedback` | 反馈汇总 + Prompt diff apply |
| `/settings` | 数据源接入向导 + 三模式 Badge |

## E2E

```bash
cd ../V6
BFF_PORT=8788 python -m src.main run-bff &
cd ../platform-v6 && npm run dev &
PLATFORM_BASE=http://127.0.0.1:3001 BFF_BASE=http://127.0.0.1:8788 \
  PYTHONPATH=. python ../V6/scripts/platform_frontend_e2e.py --skip-mutations
```
