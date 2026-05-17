# Demo 数据集

供 **代码评审与本地复现** 使用的固定样本，对应一条北京无人驾驶航空器管理相关事件。

| 文件 | 说明 |
|------|------|
| `events.json` | 1 条事件，含 `event_press_zh` 与 QA 元数据（score=95） |
| `articles.json` | 4 篇关联稿 |
| `event_article_map.json` | 事件—文章映射 |

**演示事件 ID**：`666eb4ad-9054-4ca8-8db6-8b800eadac9a`

```bash
cp data/demo/*.json data/
PYTHONPATH=. python -m src.main run-bff
```

前端访问：`/events/666eb4ad-9054-4ca8-8db6-8b800eadac9a`（需 `platform` 已启动并配置 `BFF_BASE_URL`）。

完整步骤见仓库根目录 [README.md](../../README.md) 第 5 节。
