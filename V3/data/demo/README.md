# Git 演示数据（北京无人机事件簇）

本目录为**可提交仓库**的脱敏演示包，对应一条完整事件：

- 4 篇关联稿件（含人大网代表稿 + 成员稿）
- 1 条 `event_press_zh` 中文通稿（DeepSeek 生成样例）
- QA 分数 95、`event_press_qa_*` 元数据

## 在前端演示

```bash
# 终端 1：加载演示数据并启动 BFF
cd V3
cp data/demo/*.json data/
PYTHONPATH=. python -m src.main run-bff

# 终端 2：前端
cd platform
npm install && npm run dev
# 打开 http://localhost:3000/events/666eb4ad-9054-4ca8-8db6-8b800eadac9a
```

未启动 BFF 时，前端仍可用 `lib/mock/events.ts` 中的同 ID 事件浏览。

## 事件 ID

`666eb4ad-9054-4ca8-8db6-8b800eadac9a`
