# 向量去重 + 事件聚类 + 测试落库

- 时间（UTC）：`2026-05-14T14:54:36.961940+00:00`
- 输入：`/Users/corrine/Desktop/programming/Cursor/微信公众号自动化项目/V3/data/trump_xi_summit_dedupe_test_input.json`
- 落库目录：`/Users/corrine/Desktop/programming/Cursor/微信公众号自动化项目/V3/data/dedupe_cluster_test_trump_xi`
- 抓取成功：**5** 失败：**0**
- 转载合并去掉条数：**0**
- 事件簇数：**2**
- 写入 ``ArticleRecord`` 条数：**2**（每簇一条代表稿）

## 转载级合并（余弦 ≥ 阈值）

*无转载级合并。*

## 事件簇（并查集事件边）

### 簇 0（4 篇 canonical）

1. Xi warns Trump Taiwan issue could jeopardize U.S.
   - `https://www.cnbc.com/2026/05/14/trump-xi-beijing-summit-trade-taiwan-ai-iran-rare-earths-tariffs.html`
2. Trump in China: Xi Jinping welcomes US president but thorny issues remain
   - `https://www.bbc.com/news/articles/cdxpypg9dgeo`
3. Xi tells US CEOs on Trump visit that China will open up more
   - `https://www.businesstimes.com.sg/international/global/xi-tells-us-ceos-trump-visit-china-will-open-more`
4. 习近平向随特朗普访华的美国企业高管表示：中国将进一步开放
   - `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260514-%E4%B9%A0%E8%BF%91%E5%B9%B3%E5%90%91%E9%9A%8F%E7%89%B9%E6%9C%97%E6%99%AE%E8%AE%BF%E5%8D%8E%E7%9A%84%E7%BE%8E%E5%9B%BD%E4%BC%81%E4%B8%9A%E9%AB%98%E7%AE%A1%E8%A1%A8%E7%A4%BA-%E4%B8%AD%E5%9B%BD%E5%B0%86%E8%BF%9B%E4%B8%80%E6%AD%A5%E5%BC%80%E6%94%BE`

### 簇 1（1 篇 canonical）

1. 杨丹旭：特朗普访华的面子与里子
   - `https://www.zaobao.com.sg/news/china/story20260513-9038407`

## 事件连边预览

- cos=0.79287 `https://www.cnbc.com/2026/05/14/trump-xi-beijing-summit-trade-taiwan-ai-iran-rare-earths-tariffs.html` ⟷ `https://www.bbc.com/news/articles/cdxpypg9dgeo`
- cos=0.82074 `https://www.bbc.com/news/articles/cdxpypg9dgeo` ⟷ `https://www.businesstimes.com.sg/international/global/xi-tells-us-ceos-trump-visit-china-will-open-more`
- cos=0.80813 `https://www.businesstimes.com.sg/international/global/xi-tells-us-ceos-trump-visit-china-will-open-more` ⟷ `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260514-%E4%B9%A0%E8%BF%91%E5%B9%B3%E5%90%91%E9%9A%8F%E7%89%B9%E6%9C%97%E6%99%AE%E8%AE%BF%E5%8D%8E%E7%9A%84%E7%BE%8E%E5%9B%BD%E4%BC%81%E4%B8%9A%E9%AB%98%E7%AE%A1%E8%A1%A8%E7%A4%BA-%E4%B8%AD%E5%9B%BD%E5%B0%86%E8%BF%9B%E4%B8%80%E6%AD%A5%E5%BC%80%E6%94%BE`

## 高相似对（预览）

- **0.82074** `https://www.bbc.com/news/articles/cdxpypg9dgeo` ⟷ `https://www.businesstimes.com.sg/international/global/xi-tells-us-ceos-trump-visit-china-will-open-more`
- **0.80813** `https://www.businesstimes.com.sg/international/global/xi-tells-us-ceos-trump-visit-china-will-open-more` ⟷ `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260514-%E4%B9%A0%E8%BF%91%E5%B9%B3%E5%90%91%E9%9A%8F%E7%89%B9%E6%9C%97%E6%99%AE%E8%AE%BF%E5%8D%8E%E7%9A%84%E7%BE%8E%E5%9B%BD%E4%BC%81%E4%B8%9A%E9%AB%98%E7%AE%A1%E8%A1%A8%E7%A4%BA-%E4%B8%AD%E5%9B%BD%E5%B0%86%E8%BF%9B%E4%B8%80%E6%AD%A5%E5%BC%80%E6%94%BE`
- **0.79287** `https://www.cnbc.com/2026/05/14/trump-xi-beijing-summit-trade-taiwan-ai-iran-rare-earths-tariffs.html` ⟷ `https://www.bbc.com/news/articles/cdxpypg9dgeo`
- **0.72984** `https://www.cnbc.com/2026/05/14/trump-xi-beijing-summit-trade-taiwan-ai-iran-rare-earths-tariffs.html` ⟷ `https://www.businesstimes.com.sg/international/global/xi-tells-us-ceos-trump-visit-china-will-open-more`
- **0.70087** `https://www.bbc.com/news/articles/cdxpypg9dgeo` ⟷ `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260514-%E4%B9%A0%E8%BF%91%E5%B9%B3%E5%90%91%E9%9A%8F%E7%89%B9%E6%9C%97%E6%99%AE%E8%AE%BF%E5%8D%8E%E7%9A%84%E7%BE%8E%E5%9B%BD%E4%BC%81%E4%B8%9A%E9%AB%98%E7%AE%A1%E8%A1%A8%E7%A4%BA-%E4%B8%AD%E5%9B%BD%E5%B0%86%E8%BF%9B%E4%B8%80%E6%AD%A5%E5%BC%80%E6%94%BE`
- **0.68036** `https://www.bbc.com/news/articles/cdxpypg9dgeo` ⟷ `https://www.zaobao.com.sg/news/china/story20260513-9038407`
- **0.67484** `https://www.zaobao.com.sg/news/china/story20260513-9038407` ⟷ `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260514-%E4%B9%A0%E8%BF%91%E5%B9%B3%E5%90%91%E9%9A%8F%E7%89%B9%E6%9C%97%E6%99%AE%E8%AE%BF%E5%8D%8E%E7%9A%84%E7%BE%8E%E5%9B%BD%E4%BC%81%E4%B8%9A%E9%AB%98%E7%AE%A1%E8%A1%A8%E7%A4%BA-%E4%B8%AD%E5%9B%BD%E5%B0%86%E8%BF%9B%E4%B8%80%E6%AD%A5%E5%BC%80%E6%94%BE`
- **0.62997** `https://www.cnbc.com/2026/05/14/trump-xi-beijing-summit-trade-taiwan-ai-iran-rare-earths-tariffs.html` ⟷ `https://www.rfi.fr/cn/%E4%B8%AD%E5%9B%BD/20260514-%E4%B9%A0%E8%BF%91%E5%B9%B3%E5%90%91%E9%9A%8F%E7%89%B9%E6%9C%97%E6%99%AE%E8%AE%BF%E5%8D%8E%E7%9A%84%E7%BE%8E%E5%9B%BD%E4%BC%81%E4%B8%9A%E9%AB%98%E7%AE%A1%E8%A1%A8%E7%A4%BA-%E4%B8%AD%E5%9B%BD%E5%B0%86%E8%BF%9B%E4%B8%80%E6%AD%A5%E5%BC%80%E6%94%BE`
- **0.6204** `https://www.businesstimes.com.sg/international/global/xi-tells-us-ceos-trump-visit-china-will-open-more` ⟷ `https://www.zaobao.com.sg/news/china/story20260513-9038407`
- **0.56513** `https://www.cnbc.com/2026/05/14/trump-xi-beijing-summit-trade-taiwan-ai-iran-rare-earths-tariffs.html` ⟷ `https://www.zaobao.com.sg/news/china/story20260513-9038407`
