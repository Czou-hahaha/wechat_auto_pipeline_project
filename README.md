# 微信公众号自动内容管道（可开源小项目）

这个项目将以下流程自动化（与代码实际执行顺序一致）：

**定时任务触发 -> 搜索 -> 筛选去重 -> 调用大模型摘要 -> 发送到公众号草稿箱 -> 写入本地 published 记录**

项目内所有文档均为中文，适合直接上传 GitHub 后给其他同学复用。

---

## 1. 功能说明
- 每日固定两次调度（默认 08:00 / 20:00）
- 多关键词搜索（3工具链：Google News RSS -> DDGS主工具 -> DDGS兜底工具）
- 每种搜索工具都按同一策略执行：先目标站点 `site:domain` 检索，再做全域关键词检索补充
- 每个搜索工具超时自动重试，单工具最多重试 3 次
- 当 3 个工具都失败/无结果时，暂停本次任务并返回错误
- 自动排除百科类站点（如百度百科、维基百科等）
- URL + 标题相似度 + 正文相似度去重（去重命中则跳过，不进入摘要与发布）
- 调用 DeepSeek 生成摘要
- 调用微信公众号草稿 API（`draft/add`）入草稿箱
- 草稿写入成功后，文章记录写入本地 `data/articles.json`

---

## 2. 项目结构
```text
wechat_auto_pipeline_project/
├── .env.example
├── requirements.txt
├── README.md
├── docs/
│   ├── 流程图.md
│   ├── PRD.md
│   ├── 一致性清单.md
│   └── summary_prompt.md
└── src/
    ├── main.py
    ├── config.py
    ├── search.py
    ├── ai.py
    ├── wechat.py
    ├── storage.py
    └── pipeline.py
```

---

## 3. 本地部署步骤

### 3.1 环境准备
- Python 3.9+
- 可访问外网（用于新闻检索、模型接口、微信接口）

### 3.2 安装依赖
```bash
cd wechat_auto_pipeline_project
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.3 配置环境变量
```bash
cp .env.example .env
```

至少要填：
- `WECHAT_MP_APP_ID`
- `WECHAT_MP_APP_SECRET`
- `WECHAT_MP_THUMB_MEDIA_ID`（推荐）或 `WECHAT_MP_THUMB_LOCAL_PATH`

建议填：
- `DEEPSEEK_API_KEY`

---

## 4. 公众号打通流程（重点）

### 4.1 获取公众号开发信息
1. 登录微信公众平台。
2. 进入开发设置，拿到 `AppID`、`AppSecret`。
3. 填入 `.env`：
   - `WECHAT_MP_APP_ID=...`
   - `WECHAT_MP_APP_SECRET=...`

### 4.2 准备封面素材（两种方式）

方式 A（推荐）：直接使用已上传的 `thumb_media_id`
- 在公众号后台素材库上传一张封面图。
- 填 `WECHAT_MP_THUMB_MEDIA_ID=xxx`。

方式 B：用本地文件自动上传
- 填 `WECHAT_MP_THUMB_LOCAL_PATH=/绝对路径/cover.jpg`
- 首次运行会自动调微信素材接口上传。

### 4.3 联调验证
运行单次任务：
```bash
python -m src.main run-once
```

看到日志里成功统计后，去公众号后台草稿箱确认是否生成了新草稿。

---

## 5. 运行方式

### 5.1 手动执行一次
```bash
python -m src.main run-once
```

### 5.2 启动定时任务常驻
```bash
python -m src.main run-scheduler
```

默认按照：
- `SCHEDULE_MORNING_HOUR=8`
- `SCHEDULE_EVENING_HOUR=20`
- `SCHEDULE_TIMEZONE=Asia/Shanghai`

---

## 6. 关键配置项
- `SEARCH_QUERIES`：逗号分隔关键词
- `SEARCH_TARGET_SITES`：逗号分隔目标域名（先站点后全域）
- `SEARCH_MAX_RESULTS`：每个关键词检索上限
- `MAX_ARTICLE_AGE_HOURS`：发布时间窗口（小时）
- `MAX_PUBLISH_PER_RUN`：单次最多发布条数

说明：
- 搜索重试次数当前固定为 3（代码内常量），未开放环境变量配置。
- 搜索工具链当前固定为：Google RSS -> DDGS主工具 -> DDGS兜底工具。
- DeepSeek 摘要书写规范来自 `docs/summary_prompt.md`，摘要前会先加载该文档。

---

## 7. 常见问题

### Q1: 运行成功但草稿箱没有内容
- 检查 `WECHAT_MP_APP_ID/SECRET` 是否正确。
- 检查封面参数是否有效（`thumb_media_id` 或本地封面路径）。
- 检查日志里是否有微信 `errcode`。

### Q2: 摘要质量不稳定
- 优先配置 `DEEPSEEK_API_KEY`。
- 确认原文抓取到的正文长度是否足够。

### Q3: 总是没有检索结果
- 先确认网络可访问 Google（DDGS 会自动选择可用后端）。
- 观察日志中的 `search tool=... failed on attempt=...`，定位是哪个工具连续超时。
- 放宽关键词或增大结果数。

---

## 8. 对外开源建议
- 不要提交 `.env`
- 提交 `.env.example`
- 在仓库 README 保留“公众号接入步骤”
- 首次发布时附带 `docs/流程图.md`、`docs/PRD.md`、`docs/一致性清单.md`
