# 搜索存档 → 抓取 → 向量去重 / 事件聚类 — 阅读摘要

- 生成时间（UTC）：`2026-05-14T01:13:34.696005+00:00`
- 输入文件：`/Users/corrine/Desktop/programming/Cursor/微信公众号自动化项目/V3/data/test_search_results.json`
- 输入条数：**7**
- 全文抓取成功：**7**  失败：**0**
- 向量后端：**local**  模型：`BAAI/bge-m3`

## 1. 抓取成功条目（去重前）

| # | 标题（截断） | URL | 正文字数 |
|---|--------------|-----|----------|
| 1 | The Hidden Tradeoffs Powering Joby’s eVTOL Motors | https://spectrum.ieee.org/evtol-joby-jon-wagner-motors | 3702 |
| 2 | 36氪首发｜新加坡博士团队创业获种子轮融资，首款产品做“会飞的家庭管家” | https://36kr.com/p/3805672617959173?f=rss | 2018 |
| 3 | If DJI drones are so dangerous, why are they still flying in | https://dronedj.com/2026/05/12/dji-autel-drone-ban-fcc/ | 9472 |
| 4 | Is the UK’s RAE(F) and SAIL Marking System Becoming an Expen | https://www.suasnews.com/2026/05/is-the-uks-raef-and-sail-marking-system-becoming-an-expensive-double-check-on-drone-manufacturers/ | 9409 |
| 5 | CubePilot France – Embedded & Safety Critical Software Engin | https://www.suasnews.com/2026/05/cubepilot-france-embedded-safety-critical-software-engineer/ | 2313 |
| 6 | Airbility Signs Strategic MoU with Germany’s Schübeler onEDF | https://www.suasnews.com/2026/05/airbility-signs-strategic-mou-with-germanys-schubeler-onedf-propulsion-technology-for-evtol-platforms/ | 3076 |
| 7 | UAV Navigation–Grupo Oesía Launches VECTOR - 300, a New Auto | https://www.suasnews.com/2026/05/uav-navigation-grupo-oesia-launches-vector-300-a-new-autopilot-designed-for-mass-production-of-loitering-munitions-and-c-uas-interceptors/ | 3553 |

## 2. 向量去重 / 事件聚类结果

- **模式**：`embedding_reprint_plus_event`
- **向量耗时（秒）**：10.58
- **转载合并去掉条数**（余弦 ≥ 0.9）：**0**
- **事件簇个数**：**7**

### 2.1 转载级去重（被去掉的 URL → 保留的 canonical）

*本批没有出现「转载级」合并（没有两条同时达到转载余弦阈值）。*

### 2.2 事件簇（每簇 = 同一事件；簇内多篇会进同一 `summarize_cluster`）

**事件 0**（1 篇）
- 1. The Hidden Tradeoffs Powering Joby’s eVTOL Motors
  - `https://spectrum.ieee.org/evtol-joby-jon-wagner-motors`

**事件 1**（1 篇）
- 1. 36氪首发｜新加坡博士团队创业获种子轮融资，首款产品做“会飞的家庭管家”
  - `https://36kr.com/p/3805672617959173?f=rss`

**事件 2**（1 篇）
- 1. If DJI drones are so dangerous, why are they still flying in US?
  - `https://dronedj.com/2026/05/12/dji-autel-drone-ban-fcc/`

**事件 3**（1 篇）
- 1. Is the UK’s RAE(F) and SAIL Marking System Becoming an Expensive Double
  - `https://www.suasnews.com/2026/05/is-the-uks-raef-and-sail-marking-system-becoming-an-expensive-double-check-on-drone-manufacturers/`

**事件 4**（1 篇）
- 1. CubePilot France – Embedded & Safety Critical Software Engineer – sUAS News
  - `https://www.suasnews.com/2026/05/cubepilot-france-embedded-safety-critical-software-engineer/`

**事件 5**（1 篇）
- 1. Airbility Signs Strategic MoU with Germany’s Schübeler onEDF Propulsion Technology for eVTOL Platfor
  - `https://www.suasnews.com/2026/05/airbility-signs-strategic-mou-with-germanys-schubeler-onedf-propulsion-technology-for-evtol-platforms/`

**事件 6**（1 篇）
- 1. UAV Navigation–Grupo Oesía Launches VECTOR - 300, a New Autopilot Designed for Mass Production of Lo
  - `https://www.suasnews.com/2026/05/uav-navigation-grupo-oesia-launches-vector-300-a-new-autopilot-designed-for-mass-production-of-loitering-munitions-and-c-uas-interceptors/`

### 2.3 高相似对 Top20（仅预览；未达转载阈值则不会合并）

- **0.64036**  `https://dronedj.com/2026/05/12/dji-autel-drone-ban-fcc/` ⟷ `https://www.suasnews.com/2026/05/is-the-uks-raef-and-sail-marking-system-becoming-an-expensive-double-check-on-drone-manufacturers/`
- **0.59703**  `https://spectrum.ieee.org/evtol-joby-jon-wagner-motors` ⟷ `https://www.suasnews.com/2026/05/airbility-signs-strategic-mou-with-germanys-schubeler-onedf-propulsion-technology-for-evtol-platforms/`
- **0.56587**  `https://www.suasnews.com/2026/05/cubepilot-france-embedded-safety-critical-software-engineer/` ⟷ `https://www.suasnews.com/2026/05/airbility-signs-strategic-mou-with-germanys-schubeler-onedf-propulsion-technology-for-evtol-platforms/`

## 3. 无向量时的正文/标题近重复预览（SequenceMatcher）

*无命中对。*

## 4. 原始机器报告

完整 JSON：`/Users/corrine/Desktop/programming/Cursor/微信公众号自动化项目/V3/data/dedupe_report_from_saved_search.json`
