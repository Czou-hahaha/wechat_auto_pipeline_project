# 低空经济 Event Intelligence（V3）

> 仓库主版本：**V3 后端流水线** + **platform 情报前端**  
> 历史 V1/V2 开源骨架见 [GitHub 原 README 结构](https://github.com/Czou-hahaha/wechat_auto_pipeline_project)；本仓库目录以 V3 为准。

面向**低空经济 / 无人机 / eVTOL** 的多源新闻采集与 **Event 级情报** 平台：不是 article 列表，而是「事件 → AI 通稿 → 溯源 → QA」。

---

## 仓库结构

```
├── V3/                 # Python 流水线（检索、聚类、通稿、QA、BFF）
├── platform/           # Next.js 情报前端（Dashboard / Events / Detail / QA / Search / 采集配置）
├── event_enhancement/  # 阶段三：事件扩搜（PostgreSQL 或 JSON 模式）
└── README.md           # 本文件
```

---

## 能力总览

| 能力 | 后端 (V3) | 前端 (platform) |
|------|-----------|-----------------|
| 多源检索 | RSS、GDELT、栏目页 `html_list` | 采集配置 → 数据源 / 关键词 |
| 事件聚类 | 向量 / 主题键 → `events.json` | Events 列表 |
| AI 通稿 | `event_press_zh`（DeepSeek） | Event Detail 中通稿 + 段落溯源 |
| QA | `qa_rewrite` 模块 | QA Review、分数与 diff |
| 定时采集 | `run-scheduler` + `.env` SCHEDULE_* | 采集配置 → 定时任务 Tab |
| 演示 | `V3/data/demo/` | Mock + BFF 联调 |

---

## 5 分钟演示（无需外网检索）

使用仓库自带的**北京无人机法规**演示包（含通稿 + QA 95 分）。

### 1. 后端 BFF

```bash
cd V3
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp data/demo/*.json data/
PYTHONPATH=. python -m src.main run-bff
# → http://127.0.0.1:8787/health
```

### 2. 前端

```bash
cd platform
npm install
echo 'BFF_BASE_URL=http://127.0.0.1:8787' > .env.local
npm run dev
# → http://localhost:3000
```

### 3. 建议浏览路径

1. [Dashboard](http://localhost:3000) — 指标与趋势  
2. [Events](http://localhost:3000/events) — 事件卡片  
3. [Event Detail（演示事件）](http://localhost:3000/events/666eb4ad-9054-4ca8-8db6-8b800eadac9a) — 通稿 / 溯源 / QA  
4. [采集配置](http://localhost:3000/settings) — 数据源、关键词、**定时 08:00 / 20:00**  

未启动 BFF 时前端自动使用内置 Mock，仍可浏览 UI。

---

## 生产跑全链路

```bash
cd V3
cp .env.example .env
# 必填：DEEPSEEK_API_KEY；扩搜可选 EVENT_ENHANCEMENT_DATABASE_URL
PYTHONPATH=. python -m src.main run-once
```

配置说明见 [V3/.env.example](V3/.env.example)、[V3/README.md](V3/README.md)。

---

## 与旧版（GitHub 原仓库）的关系

原 [wechat_auto_pipeline_project](https://github.com/Czou-hahaha/wechat_auto_pipeline_project) 为 **article → 摘要 → 微信草稿** 单链路。  
**V3** 在此基础上增加：

- Event 聚类与 `events.json` / `event_article_map.json`
- 事件级中文通稿（阶段四）与 QA 重写（阶段五）
- 事件扩搜（阶段三）
- Web 情报平台（`platform/`）

---

## 安全

- 勿提交 `.env`；仅使用 `.env.example` 占位  
- 若曾将 API Key 写入示例文件，请在服务商侧**轮换密钥**

---

## License

与作者原仓库策略一致；商用前请自行核对各数据源与模型服务条款。
