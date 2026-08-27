# 第 12 周：多模态 KB + CRAG + 总复盘

> **前置**：第 11 周 Graph RAG（Neo4j）已验收。  
> **本周主题**：截图/架构图/幻灯走 **生产级多模态检索**；易失败题挂 **CRAG**；收口扩展法复盘。  
> **原则**：图像为唯一事实源；`KB → Profile → Tool → Agent`。

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
- **本轮检索面**：VLM caption 后的文本 hybrid + rerank（企业截图/幻灯问答的主流生产路径）。
- **明确后置**：本地 CLIP / 多向量跨模态双塔（见 `production-gap` 触发条件）。

配置：`VISION_MODEL`（默认 `qwen-vl-max`）、`VISION_CAPTION_CACHE_DIR`。

### CRAG

- policies Profile 声明 `crag_enabled=True`；另需 `CRAG_ENABLED=true` 才执行（全局 kill switch）。
- `incorrect` → 改写 query 再检索一次；不循环。

---

## 交付清单（DoD）

| # | 交付 | 验收 |
|---|------|------|
| 1 | `kb_multimodal/images/*.png` 为唯一语料 | 无手写答案 MD 参与 ingest |
| 2 | VLM caption 入库 + 缓存 | source 指向图像路径；`media_path` 入元数据 |
| 3 | `search_visual` + Registry | routing 选中 visual 题 |
| 4 | CRAG Profile 钩子 | 单测覆盖控制流 |
| 5 | 总复盘 | KB × Profile × 工具 |

```bash
uv run python -m rag_assistant.pipeline --ingest --only kb_multimodal --reset
uv run python -m rag_assistant.pipeline --react --query "架构图里订单服务连到哪些下游？"
uv run python tests/eval/run_routing.py
uv run pytest tests/ --ignore=tests/eval -q
```

---

## 进度

| 项 | 状态 |
|----|------|
| 分支 `week12/multimodal-crag` | 已开（不合 main） |
| PNG 事实源 + VLM caption 入库 | **已落地**（`qwen-vl-max`，15 chunks，source=*.png） |
| 手写图说 MD | **已删除** |
| CRAG Profile 钩子 | 已落地 |
| routing | **12/12**（含 3 道 visual） |
| ReAct visual | 架构图 / 发布看板通过；引用指向 PNG |
| 总复盘文稿 | **已写**（见下「总复盘」） |

---

## 总复盘：KB × Profile × 工具 × 路由

| KB | Profile 要点 | Agent 工具 | 后端 | 典型问法 | 路由期望 |
|----|--------------|------------|------|----------|----------|
| policies | heading 1200；`expand_parent`；`crag_enabled`（需 `CRAG_ENABLED=true`） | `search_policies` | Qdrant + OS | 年假、报销标准 | search_policies |
| tabular | 短块；不拆问、不扩父 | `search_tabular` | Qdrant + OS | 工号/分机 | search_tabular |
| pdf | fixed_window 800 | `search_pdf_handbook` | Qdrant + OS | 打印机、访客停车 | search_pdf_handbook |
| relations | COMMON（图侧） | `query_relations` | Neo4j | 隔级上级、依赖、审批链 | query_relations |
| multimodal | heading；图 VLM caption；`media_path` | `search_visual` | Qdrant + OS | 架构图/看板/幻灯页 | search_visual |

**扩展法（脱稿一句）：** 新场景 = 补语料 → 注册 KB + Profile → 挂工具 → Agent 按 description 选型；检索增强挂在 Profile，不另起系统。

**本周 before/after：** 关系题仍走图；图上问题从「无工具/靠文档碰」变为 `search_visual`，引用指向 PNG；手写图说已剔除。

**明确后置（完整系统）：** 前端上传、复合 PDF/PPT 元素解析、异步入库队列、CLIP 双塔。

---

## 相关文档

- [系统架构](./architecture.md)
- [第 11 周 Graph RAG](./week11-graph-rag.md)
- [demo vs 生产](./production-gap.md) — P2-2 / P2-3
- [12 周总计划](../ai-app-engineer-2month-plan.md)
