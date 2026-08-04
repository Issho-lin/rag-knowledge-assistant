# 本项目 vs 业界落地：差距对照与后期升级改造计划

> **读法**：每个模块都写三层——**我们现在怎么做**、**生产里通常怎么做**、**什么时候值得升级**。  
> 练习项目的实现 deliberately 简化；学落地的目标是知道「简化在哪」以及「标准方案叫什么」。  
> 与周计划对齐见 [`ai-app-engineer-2month-plan.md`](../ai-app-engineer-2month-plan.md) 第 7–12 周；与方案取舍见 [`design-choices.md`](./design-choices.md)。

### 易漏讲清单（不问也该知道）

下面这些在教程/框架里很常见，**容易让人误以为就是生产默认**——本文档会主动标出，不必等你追问：

| 本项目用的 | 容易产生的错觉 | 生产里更常见 |
|-----------|---------------|-------------|
| **Chroma 本地文件** | 「向量库 = Chroma」 | **pgvector**、**Qdrant**、**Milvus**、OpenSearch kNN、云托管向量库 |
| **`bm25.pkl` 单机文件** | 「BM25 就这样」 | **Elasticsearch / OpenSearch** 倒排索引 |
| **逻辑分库 + `where`** | 「已经分库了」 | 多租户常 **物理分库**（§2.3.1） |
| **全库 `get_scores` 再取 top-k** | 「BM25 实现没问题」 | 算法对，**工程形态**不对（§2.5） |
| **本地 cross-encoder 重排** | 「重排都要自己下模型」 | 小规模可本地；规模化常用 **Cohere Rerank API** 等托管 |
| **CLI 同步 ingest** | 「入库就是跑一条命令」 | 队列 + worker + 状态 API + 失败重试 |
| **全量 `--reset`** | 「改语料就重跑 ingest」 | 按 `doc_id` **增量 upsert/删除** |
| **ReAct 并行调工具** | 「Agent 越快越好」 | 本地 cross-encoder 需串行（`RLock`）；或托管 rerank API |

---

## 1. 总览：已接近生产 vs 仍是教学简化

| 模块 | 已接近生产常见做法 | 仍是教学简化（心里有数） |
|------|-------------------|-------------------------|
| 检索主栈 | hybrid + RRF + cross-encoder rerank | — |
| 拒答 | 低置信度阈值 + prompt 拒答 + eval 共用规则 | — |
| 可观测 | Langfuse 全链路 span | — |
| 评测 | golden + keyword + recall@k + 多路对照 | 未上 Ragas / 人工评审流程 |
| 多库 | KB Registry + Profile + `--kb` + **召回阶段 metadata 下推** | **逻辑分库**（单 Chroma + 单 BM25）；非物理隔离；无 Agent 自动选库 |
| 语料 ETL | 多格式 loader、按类型切块 | pypdf 直抽；无版面解析/OCR 管线 |
| BM25 | 算法正确，小库够用 | **`bm25.pkl` 单机** + 全库 `get_scores`，非 ES 倒排 |
| 向量库 | hybrid 召回思路对 | **Chroma 本地嵌入式**——学习/PoC 友好，**非严肃生产主力**（§2.3.2） |
| 入库 | 全量 `--ingest --reset` | 无增量索引、无异步任务队列 |

---

## 2. 分模块对照

### 2.1 语料入库（ETL / Parse）

| | 本项目 | 业界常见 | 触发升级的条件 |
|--|--------|----------|----------------|
| PDF | `pypdf.extract_text()` | Docling / Unstructured / MinerU → MD；或 OCR（Tesseract / 云 OCR） | 乱码、扫描件、双栏/表格多 |
| 噪声页 | 无（封面/目录一并入库） | 规则 + 版面角色分类 + 人工 preview | 真实手册批量入库 |
| HTML/MD | trafilatura / 标题清洗 | 同左或 CMS 直接导出 MD | — |
| CSV | 行转键值文本 | 同左；大表按行或按记录 id 索引 | 万行以上 CSV |
| 任务形态 | CLI 同步 `--ingest` | 队列 + worker + 失败重试 + 入库状态 API | 多租户、日更文档 |

**应知道的工具名**：Unstructured、Docling、LlamaParse、Apache Tika、PaddleOCR。

---

### 2.2 分块（Chunking）

| | 本项目 | 业界常见 | 触发升级 |
|--|--------|----------|----------|
| 制度 MD | `chunk_by_heading` | 同左（结构感知） | — |
| PDF | `fixed_window` 800 字 | 先转 MD 再 heading；或按页+标题检测 | PDF 成为主语料 |
| 父文档 | `parent_text` + 可选扩展 | Parent-Child / Small-to-Big（Dify 同款） | 长节命中子句不够用时 |
| 策略归属 | **KB Profile**（Week 8） | 每文档类型/每租户一套 Profile | 已在做 |

---

### 2.3 索引与存储

| | 本项目 | 业界常见 | 触发升级 |
|--|--------|----------|----------|
| 向量 | Chroma 本地 `data/chroma/unified` | Qdrant、Milvus、pgvector、OpenSearch kNN | 需 HA、权限、百万 chunk |
| 关键词 | `bm25.pkl` 单文件 | **Elasticsearch / OpenSearch**（BM25 + filter 一体） | chunk > 几万 |
| 分库 | **逻辑分库**（见下 §2.3.1） | 逻辑分库 **或** 物理分库（collection / 索引 / 实例级隔离） | 多租户强隔离、不同 embedding、独立扩缩容 |
| 增量 | 仅全量 `--reset` | 按 `doc_id`/`file_hash` upsert 与删除 | 语料频繁增删改 |

#### 2.3.1 逻辑分库 vs 物理分库（重要）

本项目 Week 8 采用的是 **逻辑分库**，不是物理分库。两者都常见，差别在「隔离发生在哪一层」。

| 维度 | 逻辑分库（本项目） | 物理分库（生产常见升级方向） |
|------|-------------------|------------------------------|
| **存储形态** | 一个 Chroma 路径 `data/chroma/unified`、一个 collection、一个 `bm25.pkl` | 每 KB 独立 collection（如 `policies` / `tabular` / `pdf`），或独立 `bm25_{kb}.pkl`，或独立向量库实例 |
| **如何区分库** | chunk 元数据字段 `kb`；检索时 `where={"kb": "..."}` + BM25 按下标子集 | 根本不混存；Agent/路由直接连对应索引，无需 metadata filter |
| **入库** | 一次 `--ingest` 写同一套索引 | 可按 KB 单独 ingest / reset / 版本回滚 |
| **Embedding** | 全库共用同一模型与维度 | 可为 PDF 手册、代码库、表格各用不同 embedding 模型 |
| **权限与合规** | 依赖应用层过滤；同库内数据物理相邻 | 租户 A/B 数据不在同一 collection，便于 ACL、审计、数据驻留 |
| **扩缩容** | 库变大后全库重建、全库 ANN 调参 | 只给暴涨的 `pdf` 库加副本或迁独立集群 |
| **典型产品** | Dify 多知识库常仍落同一向量后端 + metadata；小中型内网 RAG | 多租户 SaaS、跨 BU 强隔离、单库超百万 chunk |

**为什么练习项目先选逻辑分库**

1. **与 Dify/FastGPT 一类产品的心智一致**：多「知识库」是产品与 Profile 概念，底层可以仍是一个向量后端。  
2. **改动面小**：Week 8 重点是 Registry、Profile、`--kb`、召回下推——不必同时改 ingest、存储路径、engine 多实例。  
3. **当前规模**：约百级 chunk，逻辑过滤的性能与隔离都够用。  
4. **全库检索仍自然**：默认不设 `--kb` 时跨库 RRF，适合「用户不知道问的是哪类文档」。

**什么时候该升级为物理分库**

| 触发信号 | 建议动作 |
|----------|----------|
| 多租户 / 客户数据**不能进同一 collection** | 每租户或每客户独立 collection + 独立 BM25 |
| 不同 KB 要用**不同 embedding 模型** | 物理拆开（逻辑分库无法混维度） |
| 某一 KB 体量或 QPS 远大于其他库 | 只给该 KB 独立索引与副本 |
| 需要**按库独立发布**（如 PDF 日更、制度月更） | 按 KB 增量 ingest，避免全库 `--reset` |
| metadata `where` 过滤后仍偶发**跨库泄漏**或 perf 差 | 审查是否应改为物理隔离 |
| Agent 已稳定「一工具一库」 | 工具实现直接绑物理索引，路由与存储一一对应 |

**物理分库在本仓库的落点（若要做）**

```text
data/chroma/
  policies/     # collection policies
  tabular/
  pdf/
data/chroma/policies/bm25.pkl
...
```

- `kb/registry.py` 增加 `chroma_path` / `collection_name`  
- `ingest` 按 KB 写入对应 store；`engine` 按 `kb_id` 选 store 而非 `where`  
- Week 9 的 `search_policies` 等工具 → 直接调对应物理索引（与业界「一工具一库」对齐）

**和「BM25 按 kb 拆多个 pkl」的关系**：P1-1 里的「按 `kb` 拆 BM25」是 **半物理化**（关键词侧分库，向量仍逻辑统一）；全物理分库是向量 + BM25 + ingest 全链路按 KB 拆开。

#### 2.3.2 为什么用 Chroma、生产一般换什么（重要）

**结论先说**：严肃生产环境 **很少把 Chroma 当作主力向量库**。我们选它是因为 **零运维、本地文件、和 LangChain 生态教程一致**，方便把精力放在 RAG 链路上，而不是数据库运维。

| 维度 | Chroma（本项目） | 生产更常见 |
|------|------------------|-----------|
| **定位** | 嵌入式向量库，像「向量版 SQLite」 | 独立服务或 DB 扩展，像「向量版 PostgreSQL / 专用搜索引擎」 |
| **部署** | `pip install`，数据落 `data/chroma/` | Docker/K8s 集群、托管 SaaS、云厂商向量检索 |
| **适用** | PoC、学习、个人/小团队内网工具、百～十万级向量 | 百万+ chunk、多副本 HA、多租户 ACL、SLA |
| **与关键词检索** | 必须另维护 `bm25.pkl`（两套系统） | 常收敛到 **ES/OpenSearch**（BM25 + dense_vector 一体）或 **pgvector + 全文** |
| **换库成本** | 检索抽象在 `vector.py` | 换后端时主要改这一层；上层 hybrid/rerank 可保留 |

**生产按场景怎么选**（面试/落地常问）：

| 场景 | 常见选择 |
|------|----------|
| 公司已有 PostgreSQL，规模中等 | **pgvector**（少一套系统，事务/权限复用 PG） |
| 独立向量服务、要过滤/混合检索 | **Qdrant**、**Milvus**（或 Zilliz Cloud） |
| 已有 Elasticsearch/OpenSearch 栈 | **dense_vector + kNN**（关键词和向量一个集群） |
| 不想自运维、快速上线 | **Pinecone**、Azure AI Search、Vertex Vector Search 等托管 |
| 超大规模、多分片 | **Milvus**、云托管向量库 |

**Chroma 会不会上生产？** 有——极小规模内网、单实例可接受、无强隔离要求时，Chroma Server 也能跑。但那是例外，不是行业默认。教程里满屏 Chroma，不等于公司技术选型会选它。

**类比记忆**：Chroma ≈ SQLite；pgvector/Qdrant/Milvus ≈ PostgreSQL/专用数据库。学 RAG 用 SQLite 没问题；上线要问「能不能直接换 PostgreSQL」。

**本仓库升级路径**：P2-6 **托管向量库**（Chroma → Qdrant/pgvector）；若同时换关键词侧，P2-7 **ES 统一检索** 可一并考虑。

---

### 2.4 向量检索

| | 本项目 | 业界常见 | 触发升级 |
|--|--------|----------|----------|
| 召回 | embedding top-k + `where` | 同左；ANN 索引（HNSW/IVF） | 规模变大时调 HNSW 参数 |
| Query 增强 | 多轮改写、可选子查询分解 | + HyDE、多查询 RRF、同义词扩展 | 召回率瓶颈时 |
| 多向量 | 每 chunk 一个向量 | 标题/摘要/正文各一向量（FastGPT index 增强） | 长文档、标题与正文语义分离 |

---

### 2.5 BM25 / 关键词检索

| | 本项目 | 业界常见 | 触发升级 |
|--|--------|----------|----------|
| 打分 | `BM25Okapi.get_scores()` **对全库每篇算分** | **倒排索引**：只对含 query token 的 posting 算分 | chunk 上万 |
| 中文分词 | 单字 + 拉丁串（无 jieba） | jieba / pkuseg / ES ik 分词器 | 专有名词召回差 |
| 元数据过滤 | 先 `get_scores`，再筛 `kb` 下标取 top-k | ES `bool filter + must match` 在索引层完成 | 与倒排升级一并做 |
| 与向量关系 | 双写、RRF 融合 | 同左；或 ES hybrid 单引擎 | 运维想少一套系统时 |

**要点**：BM25 **算法**是标准的；**全库暴力打分**是小库 demo 做法，不是 Elasticsearch 的做法。

---

### 2.6 融合、重排、拒答

| | 本项目 | 业界常见 |
|--|--------|----------|
| 融合 | RRF（避免分数量纲问题） | 同左；或加权（需校准） |
| 重排 | 本地 bge-reranker | 同左；或 Cohere Rerank API |
| 拒答 | rerank 后统一低分过滤 + `REFUSE_MIN_RERANK_SCORE` | 同左 + 业务规则 + 澄清话术 |
| 后过滤 | `filter_chunks`：低分 + metadata 兜底 | 低分在应用层；metadata 多在索引层已过滤 |

---

### 2.7 多库与 Agent 路由

| | 本项目（Week 8） | 业界（Week 9+ 目标） |
|--|------------------|----------------------|
| 隔离方式 | **逻辑分库**（§2.3.1）；单索引 + `kb` 过滤 | 中小规模可仍逻辑；多租户 / 大库常 **物理分库** |
| 选库 | 运维/调试 `--kb`；产品默认全库 | Agent function calling 选 `search_*` 工具 |
| 注册表 | `kb/registry.py` 预留 `tool_name` | 每 KB 一个工具 + description；工具背后常绑**独立物理索引** |
| 路由评测 | 分库 golden + per-item `kb` | 单库题必须选对工具；跨库题多工具 |
| 歧义 | 未做澄清 | 「两个孙悟空」→ 追问或按上下文选库 |

---

### 2.8 评测与运维

| | 本项目 | 业界常见 |
|--|--------|----------|
| 回归 | golden 30 题 + keyword + recall@k | + Ragas、抽样人工评、线上 bad case 回流 |
| 阈值 | `score_report.py` 标定拒答 | 离线分位数 + 线上拒答率/误拒率监控 |
| 追踪 | Langfuse | 同左 + 按 `kb`/工具分桶、检索空结果率 |

---

## 3. 后期升级改造计划

与 [`ai-app-engineer-2month-plan.md`](../ai-app-engineer-2month-plan.md) 对齐；**按优先级分三档**。

### P0 — 与学习计划绑定，建议必做

| 序号 | 项 | 说明 | 计划周次 |
|------|-----|------|----------|
| P0-1 | **Week 8 收尾** | PDF 语料、re-ingest、分库 golden、`--kb` / eval 验收 | 第 8 周 |
| P0-2 | **Agent 工具路由** | KB → Tool；function calling；路由专项 eval | 第 9 周 |
| P0-3 | **分库 eval 固化** | `run.py` 支持 per-item `kb`；对比全库 vs 指定库 vs 错库 | 第 8–9 周 |
| P0-4 | **文档与面试稿同步** | architecture / interview-prep 反映多库与路由 | 第 8–9 周 |

### P1 — 工程化增强，值得在本仓库继续做

| 序号 | 项 | 现状痛点 | 目标方案 | 建议时机 |
|------|-----|----------|----------|----------|
| P1-1 | **BM25 倒排索引** | 全库 `get_scores`，库变大变慢 | 按 token 倒排 + 只对命中 posting 打分；或按 `kb` 拆多个 BM25 索引 | chunk > 5k 或 perf 变慢 |
| P1-2 | **PDF 解析管线** | pypdf 乱码/无结构 | Docling/Unstructured → MD → heading 切块；乱码走 OCR | 真实 PDF 语料上线前 |
| P1-3 | **PDF 噪声过滤** | 封面/目录入库 | 页级规则 + 可选 `is_noise_page`；ingest 日志记录 drop 原因 | 与 P1-2 同步 |
| P1-4 | **增量 ingest** | 每次全量 embedding | `doc_id` + `file_hash`；upsert/删除失效 chunk | 语料周更时 |
| P1-5 | **简化 filter_chunks** | metadata 与召回重复 | `filter_chunks` 只管低分；`source_contains` 等下推不了的条件才后置 | 随时小改 |
| P1-6 | **Ragas / 扩 golden** | keyword 评分脆 | 50+ 题；抽样 Ragas faithfulness（可选） | 第 12 周前后 |
| P1-7 | **入库 chunk 预览** | 无 Dify 式 preview | ingest 后输出抽样 chunk 或 CLI `--preview-chunks` | 接真实语料前 |

### P2 — 能力扩展，按周计划或业务需要

| 序号 | 项 | 说明 | 计划周次 |
|------|-----|------|----------|
| P2-1 | **关系 / Graph KB** | Neo4j + `query_relations`；prose 抽取建图 | **第 11 周** |
| P2-2 | **多模态 KB** | 截图/幻灯；`search_visual` | 第 11 周 |
| P2-3 | **CRAG / Self-RAG** | 挂在 Profile 上的纠错层，非另起系统 | 第 12 周 |
| P2-4 | **HyDE / 查询扩展** | 某 Profile 内开关，before/after | 第 10–12 周可选 |
| P2-5 | **物理分库** | 每 KB 独立向量 collection + 独立 BM25/ES 索引；registry 绑后端；工具直连物理索引 | 多租户隔离、不同 embedding、单库规模或独立发布 |
| P2-6 | **替换向量库后端** | Chroma → **Qdrant / pgvector / Milvus**（改 `vector.py` 抽象层） | 上生产、要 HA/扩缩容/权限时 |
| P2-7 | **ES/OpenSearch 统一检索** | BM25 + 向量 + filter 一个集群 | 运维希望少维护两套索引时 |
| P2-8 | **异步 ingest 队列** | API 上传 → 后台解析/embed | 多用户上传时 |

### 暂不优先（知道即可）

- Embedding 微调  
- 公网多租户 SaaS 部署  
- GraphRAG 全量社区摘要（Microsoft 论文级）——第 11 周做 **Neo4j + 工具路由** 即可，不必上社区层

---

## 4. 推荐执行顺序（路线图）

```text
现在 ──► Week 8 收尾（PDF、re-ingest、分库 eval）
         │
         ▼
       Week 9 Agent 路由 + 路由 golden
         │
         ├──► P1 PDF 管线 + 噪声过滤（真实 PDF 前）
         ├──► P1 分库 eval / run.py --kb
         │
         ▼
       第 10 生产存储改造（见 production-upgrade.md）
         │
         ▼
       第 11 Graph RAG（Neo4j）→ 第 12 多模态 + CRAG
```

---

## 5. 每个模块的学习自检（3 问）

改任何一层之前，先问自己：

1. **我们现在怎么做的？**（打开对应 `src/rag_assistant/` 模块）  
2. **生产默认用什么？**（工具/架构名，见上文）  
3. **什么规模或什么失败案例会逼我们升级？**（触发条件）

---

## 6. 相关文档

- [系统架构](./architecture.md)  
- [入库流水线](./ingest-pipeline.md)  
- [问答流水线](./query-pipeline.md)  
- [Chunk 数据模型](./chunk-data-model.md)  
- [关键方案说明](./design-choices.md)  
- [学习计划](../ai-app-engineer-2month-plan.md)  
