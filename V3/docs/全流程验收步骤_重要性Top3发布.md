# 全流程验收步骤（重要性 Top3 + 公众号发布）

> 更新：2026-05-19  
> 规则：**仅对 importance 最高的前 3 个事件簇做摘要**；推送时跳过 **近 3 天已推过公众号** 的同一 `topic_key` / 标题指纹。

## 一、发布规则（代码行为）

| 配置项 | 默认 | 含义 |
|--------|------|------|
| `WECHAT_PUBLISH_TOP_N` | 3 | 按 `event_enhancement.scoring.importance` 打分后，只对前 N 个簇调用 DeepSeek 摘要 + QA |
| `WECHAT_PUBLISH_COOLDOWN_DAYS` | 3 | 若历史 `articles.json` 中同 topic/标题在冷却期内已有 `wechat_draft_pushed_at`，跳过该簇 |
| `RUN_ONCE_PUSH_TO_WECHAT` | false | **true** 时摘要通过后直接 `draft/add` 写公众号草稿箱 |
| `CLUSTER_SUMMARY_MIN_CHARS` | 800 | 摘要可见字数（不含 HTML 标签）不足则 `skipped_too_short`，不发布 |

打分维度：权威源 host + 稿数 + 关键词命中 + 24h/48h 时效（见 `event_enhancement/event_enhancement/scoring/importance.py`）。

日志关键字：`summarize pick[1] importance=...`

## 二、验收前准备

### 2.1 环境

```bash
cd V3
python -V   # 3.11+
pip install -r requirements.txt
```

### 2.2 必填 `.env`

- `DEEPSEEK_API_KEY`
- `WECHAT_MP_APP_ID` / `WECHAT_MP_APP_SECRET`
- `WECHAT_MP_THUMB_LOCAL_PATH`（封面图存在）
- `MAX_ARTICLE_AGE_HOURS=14`（或所需时间窗）
- `RUN_ONCE_PUSH_TO_WECHAT=true`（本次要发公众号时）
- `EVENT_ENHANCEMENT_DATABASE_URL` 留空 = JSON 扩搜模式

### 2.3 公众号 IP 白名单

若日志出现 `40164` / IP 不在白名单：登录 [微信公众平台](https://mp.weixin.qq.com) → 开发 → 基本配置 → IP 白名单，加入服务器公网 IP（日志中会打印）。

## 三、清空历史数据（从头跑）

```bash
cd V3
STAMP=$(date -u +%Y%m%dT%H%M%S)
mkdir -p "data/backup_before_top3_${STAMP}"
cp -a data/articles.json data/events.json data/event_article_map.json \
  "data/backup_before_top3_${STAMP}/" 2>/dev/null || true
echo '[]' > data/articles.json
echo '[]' > data/events.json
echo '[]' > data/event_article_map.json
rm -f data/event_enhancement_last_run.json
```

## 四、全流程执行（单命令）

```bash
cd V3
export RUN_ONCE_PUSH_TO_WECHAT=true
export WECHAT_PUBLISH_TOP_N=3
export WECHAT_PUBLISH_COOLDOWN_DAYS=3
python -m src.main run-once 2>&1 | tee "data/run_once_top3_${STAMP}.log"
```

### 阶段对照（日志 / 产物）

| 阶段 | 做什么 | 成功标志 |
|------|--------|----------|
| 1 检索 | RSS/HTML 列表 + GDELT 主题词 | `rss aggregate: ... rows=` |
| 1b 预过滤 | 标题+摘要主题门（无 LLM） | `pre-fetch topic filter dropped` |
| 2 抓取 | 落地页正文、时间窗、政策门 | `prepared_buffer` 有入库候选 |
| 3 聚类 | 向量聚类 / topic 聚类 | `clusters overview: count=` |
| 4 选 Top3 | importance 排序 + 3 日冷却 | `summarize pick[1..3] importance=` |
| 5 摘要+QA | DeepSeek 并行度 `DEEPSEEK_CLUSTER_CONCURRENCY` | `staged_for_review` 或 `published` |
| 6 公众号 | `draft/add` | `published=N` 且无 40164 |
| 7 事件增强 | JSON 扩搜 + 向量门槛 | `event_enhancement_last_run.json` |
| 8 通稿+QA | `EVENT_AI_PRESS_ENABLED` | `events.json` 含 `event_press_zh` |

### 结束统计行

```
run_once done: candidates=... published=... staged_for_review=... skipped_summarize_cap=...
```

- `skipped_summarize_cap`：因 Top3 未进入摘要的簇数  
- `published`：本轮写入公众号草稿箱的篇数（≤3）

## 五、结果检查清单

- [ ] `data/articles.json`：≤3 条 `ready_for_review` 或 `published`，均有 `summary`
- [ ] `data/events.json`：对应事件 ≤3 条
- [ ] `data/event_article_map.json`：event ↔ article 映射完整
- [ ] 公众号后台 → 素材管理 → 草稿箱：有新草稿（需 IP 白名单）
- [ ] `data/event_enhancement_last_run.json`：`status=ok` 或扩搜记录
- [ ] （可选）Platform `http://localhost:3000` + BFF `:8787` 事件列表按 `importance_score` 排序

## 六、可选：仅补推今日草稿

若 `run-once` 因微信 token 失败只入了库未推送：

```bash
cd V3
python -m src.main push-today-drafts
```

## 七、单元测试

```bash
cd V3
python -m pytest tests/test_cluster_publish_selection.py tests/test_topic_prefilter.py -q
```

## 八、2026-05-19 实测记录（`run_once_top3_20260519T131443.log`）

| 指标 | 值 |
|------|-----|
| GDELT+RSS 候选 | 37 → 预过滤后 7 |
| 向量聚类事件 | 5 |
| **Top3 摘要** | `summarize pick[1..3] importance=40/35/35` |
| 未进摘要（cap） | `skipped_summarize_cap=2` |
| QA 通过入库 | 0（3 篇均未过 QA） |
| 公众号推送 | 0（启动时 `40164` IP `183.192.44.51` 未在白名单，整轮 `publish_to_wechat=false`） |
| 事件增强 | OK，`event_enhancement_last_run.json` 已写 |

**发布前必做**：微信公众平台添加 IP 白名单 → 再跑 `RUN_ONCE_PUSH_TO_WECHAT=true` 或 `push-today-drafts`。

## 九、相关代码

- 选簇：`V3/src/pipeline.py` → `_select_top_importance_clusters`
- 打分：`V3/src/utils/cluster_importance.py`
- 配置：`V3/src/config.py` → `WECHAT_PUBLISH_TOP_N` / `WECHAT_PUBLISH_COOLDOWN_DAYS`
