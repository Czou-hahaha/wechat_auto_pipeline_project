# 向量去重 + 事件聚类 + 测试落库

- 时间（UTC）：`2026-05-14T14:40:38.395445+00:00`
- 输入：`/Users/corrine/Desktop/programming/Cursor/微信公众号自动化项目/V3/data/beijing_drone_dedupe_test_input.json`
- 落库目录：`/Users/corrine/Desktop/programming/Cursor/微信公众号自动化项目/V3/data/dedupe_cluster_test_beijing`
- 抓取成功：**4** 失败：**1**
- 转载合并去掉条数：**0**
- 事件簇数：**1**
- 写入 ``ArticleRecord`` 条数：**1**（每簇一条代表稿）

## 转载级合并（余弦 ≥ 阈值）

*无转载级合并。*

## 事件簇（并查集事件边）

### 簇 0（4 篇 canonical）

1. 无人机神出鬼没 北京祭出最严新规禁飞禁售
   - `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260429-%E6%97%A0%E4%BA%BA%E6%9C%BA%E7%A5%9E%E5%87%BA%E9%AC%BC%E6%B2%A1-%E5%8C%97%E4%BA%AC%E7%A5%AD%E5%87%BA%E6%9C%80%E4%B8%A5%E6%96%B0%E8%A7%84%E7%A6%81%E9%A3%9E%E7%A6%81%E5%94%AE`
2. @所有无人驾驶航空器爱好者，这份提示请收好
   - `https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202604/t20260427_4617643.html`
3. 北京成中国首个禁售禁运并禁飞无人机城市
   - `https://www.zaobao.com.sg/news/china/story20260328-8807386`
4. 《北京市无人驾驶航空器管理规定》今年5月1日实施 对无人驾驶航空器飞行和销售运输存储作出新规定
   - `https://www.bjrd.gov.cn/rdzl/rdzc/fgjd/202604/t20260410_4579143.html`

## 事件连边预览

- cos=0.80611 `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260429-%E6%97%A0%E4%BA%BA%E6%9C%BA%E7%A5%9E%E5%87%BA%E9%AC%BC%E6%B2%A1-%E5%8C%97%E4%BA%AC%E7%A5%AD%E5%87%BA%E6%9C%80%E4%B8%A5%E6%96%B0%E8%A7%84%E7%A6%81%E9%A3%9E%E7%A6%81%E5%94%AE` ⟷ `https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202604/t20260427_4617643.html`
- cos=0.87744 `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260429-%E6%97%A0%E4%BA%BA%E6%9C%BA%E7%A5%9E%E5%87%BA%E9%AC%BC%E6%B2%A1-%E5%8C%97%E4%BA%AC%E7%A5%AD%E5%87%BA%E6%9C%80%E4%B8%A5%E6%96%B0%E8%A7%84%E7%A6%81%E9%A3%9E%E7%A6%81%E5%94%AE` ⟷ `https://www.zaobao.com.sg/news/china/story20260328-8807386`
- cos=0.84169 `https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202604/t20260427_4617643.html` ⟷ `https://www.zaobao.com.sg/news/china/story20260328-8807386`
- cos=0.8077 `https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202604/t20260427_4617643.html` ⟷ `https://www.bjrd.gov.cn/rdzl/rdzc/fgjd/202604/t20260410_4579143.html`
- cos=0.79497 `https://www.zaobao.com.sg/news/china/story20260328-8807386` ⟷ `https://www.bjrd.gov.cn/rdzl/rdzc/fgjd/202604/t20260410_4579143.html`

## 高相似对（预览）

- **0.87744** `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260429-%E6%97%A0%E4%BA%BA%E6%9C%BA%E7%A5%9E%E5%87%BA%E9%AC%BC%E6%B2%A1-%E5%8C%97%E4%BA%AC%E7%A5%AD%E5%87%BA%E6%9C%80%E4%B8%A5%E6%96%B0%E8%A7%84%E7%A6%81%E9%A3%9E%E7%A6%81%E5%94%AE` ⟷ `https://www.zaobao.com.sg/news/china/story20260328-8807386`
- **0.84169** `https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202604/t20260427_4617643.html` ⟷ `https://www.zaobao.com.sg/news/china/story20260328-8807386`
- **0.8077** `https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202604/t20260427_4617643.html` ⟷ `https://www.bjrd.gov.cn/rdzl/rdzc/fgjd/202604/t20260410_4579143.html`
- **0.80611** `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260429-%E6%97%A0%E4%BA%BA%E6%9C%BA%E7%A5%9E%E5%87%BA%E9%AC%BC%E6%B2%A1-%E5%8C%97%E4%BA%AC%E7%A5%AD%E5%87%BA%E6%9C%80%E4%B8%A5%E6%96%B0%E8%A7%84%E7%A6%81%E9%A3%9E%E7%A6%81%E5%94%AE` ⟷ `https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202604/t20260427_4617643.html`
- **0.79497** `https://www.zaobao.com.sg/news/china/story20260328-8807386` ⟷ `https://www.bjrd.gov.cn/rdzl/rdzc/fgjd/202604/t20260410_4579143.html`
- **0.74391** `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260429-%E6%97%A0%E4%BA%BA%E6%9C%BA%E7%A5%9E%E5%87%BA%E9%AC%BC%E6%B2%A1-%E5%8C%97%E4%BA%AC%E7%A5%AD%E5%87%BA%E6%9C%80%E4%B8%A5%E6%96%B0%E8%A7%84%E7%A6%81%E9%A3%9E%E7%A6%81%E5%94%AE` ⟷ `https://www.bjrd.gov.cn/rdzl/rdzc/fgjd/202604/t20260410_4579143.html`
