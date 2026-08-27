# 第 12 周：多模态 KB + CRAG + 总复盘

> **前置**：第 11 周 Graph RAG（Neo4j）已验收。  
> **本周主题**：截图/架构图/幻灯走 **生产级多模态检索**；易失败题挂 **CRAG**；收口扩展法复盘。  
> **状态**：**已验收（2026-08-27）** · 分支 `week12/multimodal-crag`（暂不合 main）

---

## 为什么单独一周

| 问法 | 工具 | 存储 |
|------|------|------|
| 「年假几天」 | `search_policies` | 向量 + BM25 |
| 「周凯上级是谁」 | `query_relations` | Neo4j |
| 「架构图里订单服务连了谁」「发布看板这一页写了什么」 | **`search_visual`** | 图像 → VLM caption → 向量 + BM25 |

CRAG 不是新工具，而是 **Profile 上的纠错层**。

---

## 生产形态（本周定案）

```text
images/*.png（唯一事实源）
        │
        ▼
 Vision 模型自动 caption（file_hash 缓存；失败显式报错）
        │
        ▼
 Document(source=图像路径, kind=image, media_path=...)
        │
        ▼
 Qdrant collection=multimodal + OpenSearch index=multimodal
        │
        ▼
 search_visual → Observation（caption 文本 + media_path）
```

- **禁止**：用手写 Markdown 图说冒充多模态索引内容。
- **本轮检索面**：VLM caption 后的文本 hybrid + rerank。
- **明确后置**：复合 PDF/PPT 元素解析、回答回灌原图、CLIP 双塔、前端上传。

配置：`VISION_MODEL`（默认 `qwen-vl-max`）、`VISION_CAPTION_CACHE_DIR`；CRAG 需 `CRAG_ENABLED=true` + policies Profile。

---

## 交付清单（DoD）— 全部完成

| # | 交付 | 验收 |
|---|------|------|
| 1 | `kb_multimodal/images/*.png` 为唯一语料 | 无手写答案 MD |
| 2 | VLM caption 入库 + 缓存 | source=*.png；15 chunks |
| 3 | `search_visual` + Registry | routing **12/12** |
| 4 | CRAG Profile 钩子 | 单测 + 手测 before/after |
| 5 | 总复盘 | 见下表 |

---

## 验收记录（2026-08-27）

| 项 | 结果 |
|----|------|
| 单测 | **77** passed |
| routing | **12/12**（含 visual ×3） |
| ReAct visual | 架构图 / 看板通过；引用 PNG |
| CRAG 手测 | 问「星云协作订单链路里支付之后还打谁？」强制 `kb=policies`：关 CRAG → rerank 滤空 **0** 条；开 `CRAG_ENABLED=true` → grade incorrect → rewrite → **2** 条（产品说明等） |
| 多模态不回归 | `CRAG_ENABLED=true` 下 `search_visual` 仍答对订单下游 |

---

## 总复盘：KB × Profile × 工具 × 路由

| KB | Profile 要点 | Agent 工具 | 后端 | 典型问法 | 路由期望 |
|----|--------------|------------|------|----------|----------|
| policies | heading 1200；`expand_parent`；`crag_enabled`（需全局开关） | `search_policies` | Qdrant + OS | 年假、报销标准 | search_policies |
| tabular | 短块；不拆问、不扩父 | `search_tabular` | Qdrant + OS | 工号/分机 | search_tabular |
| pdf | fixed_window 800 | `search_pdf_handbook` | Qdrant + OS | 打印机、访客停车 | search_pdf_handbook |
| relations | COMMON（图侧） | `query_relations` | Neo4j | 隔级上级、依赖、审批链 | query_relations |
| multimodal | heading；VLM caption；`media_path` | `search_visual` | Qdrant + OS | 架构图/看板/幻灯页 | search_visual |

**扩展法（脱稿一句）：** 新场景 = 补语料 → 注册 KB + Profile → 挂工具 → Agent 按 description 选型；检索增强挂在 Profile，不另起系统。

**本周 before/after：** 图上问题有 `search_visual`；CRAG 在滤空后可改写再检索一次。

---

## 相关文档

- [系统架构](./architecture.md)
- [第 11 周 Graph RAG](./week11-graph-rag.md)
- [demo vs 生产](./production-gap.md) — P2-2 / P2-3
- [12 周总计划](../ai-app-engineer-2month-plan.md)
