# 学习路线图（全 12 周 · 一张表看清全局）

> **为什么有这份文档**：`ai-app-engineer-2month-plan.md` 是详细周计划；`production-gap.md` 是 demo vs 生产对照。  
> 本文档把两者**合成一张执行面**：每周做什么、交什么、**不问也该知道的生产认知**、当前状态。  
> 每周日更新「当前指针」；日记仍写 [`learning-log.md`](../learning-log.md)。

---

## 文档地图（迷路时先看这里）

| 文档 | 用途 | 何时读 |
|------|------|--------|
| **本文档** `learning-roadmap.md` | 全局进度、当前周、每周 DoD + 生产认知 | 每周开始/周日复盘 |
| [`ai-app-engineer-2month-plan.md`](../ai-app-engineer-2month-plan.md) | 每周必做细项、架构目标、风险 | 开工某周前细读该周章节 |
| [`production-gap.md`](./production-gap.md) | demo 简化在哪、生产换什么、P0–P2 改造 | 每完成一周扫对应模块；遇选型问题查 |
| [`learning-log.md`](../learning-log.md) | 决策、数字、踩坑实录 | 每天/每周追加 |
| [`rag-pitfalls.md`](../rag-pitfalls.md) | 真实踩坑（事后） | 撞上再写 |
| [`design-choices.md`](./design-choices.md) | 为什么这样选 | 改方案前查 |
| [`interview-prep.md`](./interview-prep.md) | 口述稿 | 复盘周更新 |

---

## 当前指针（2026-08-02 更新）

| 项 | 状态 |
|----|------|
| **已完成** | 第 1–8 周（含分库 eval **34/34**、`recall@4` 31/31） |
| **第 8 周 DoD** | ✅ 已全部达成 |
| **下一周唯一动作** | **第 9 周**：KB → Agent Tool；function calling 路由；路由专项 golden |
| **不要提前做** | 物理分库、换 Qdrant、GraphRAG、多模态（见 P2 路线图） |

---

## 全景：12 周 × 交付 × 生产认知

> **生产认知列**：每周开工前就应知道，不等你追问。详细展开见 `production-gap.md` 对应节。

| 周 | 主题 | 关键交付（DoD） | 生产认知（本周必须建立） | 状态 |
|----|------|----------------|-------------------------|------|
| **1** | 最简 RAG baseline | ingest→retrieve→generate；中文内部语料 | Embedding 走 API 可以上生产；**Chroma 本地是教学选型**（§2.3.2） | ✅ |
| **2** | 可观测 + eval 基线 | Langfuse；golden 15 题；keyword 评分 | 没有 trace + 回归集 = 无法迭代；生产必做可观测 | ✅ |
| **3** | hybrid + rerank | BM25+RRF+rerank；三路可切换 | hybrid 主栈是生产常见形态；**BM25 全库打分是 demo 形态**（§2.5） | ✅ |
| **4** | Eval 体系 | golden 30；recall@k；三路一键对照 | 分数同分不代表方案无效；要会读 recall 与 pass 分层 | ✅ |
| **5** | 产品形态 | 引用、拒答、多轮改写、Gradio | 拒答阈值要离线标定；产品与 eval 共用 `is_refusal()` | ✅ |
| **6** | 复盘固化 | architecture、demo、pitfalls、口述 | 能脱稿讲链路；手册只记真实踩坑 | ✅ |
| **7** | 检索增强 | filter、decompose、parent；enhanced 对照 | 增强项是 Profile 素材，默认关；生产按库开关 | ✅ |
| **8** | 多 KB + Profile + PDF | Registry；逻辑分库；`--kb`；PDF 语料；分库 golden | **逻辑分库 ≠ 物理分库**（§2.3.1）；召回阶段下推 filter | ✅ |
| **9** | Agent 工具路由 | 每 KB 一 Tool；routing eval；Langfuse 记 tool | 生产多库常「一工具一库」→ 背后常是**物理索引** | ⏳ |
| **10** | 关系 / Graph KB | 补关系语料；`query_relations`；路由题 | 文档 RAG 与图检索分工；HyDE 可选对照 | ⏳ |
| **11** | 多模态 KB | 补图文语料；`search_visual`；路由题 | 图→描述再检索是常见折中；真多模态 embedding 更重 | ⏳ |
| **12** | CRAG + 总复盘 | Profile 挂纠错层；KB×Profile×Tool 总表 | 纠错挂在库内而非另起系统；面试能讲扩展法 | ⏳ |

---

## 第 8 周收尾清单（复制执行）

```bash
uv run python -m rag_assistant.pipeline --ingest --reset
uv run pytest tests/test_retrieval.py tests/test_kb_registry.py -q
uv run python tests/eval/run.py          # 或先 --limit 34 看分库 4 题
uv run python tests/eval/score_report.py # 阈值仍 OK 则不动 .env
```

- [ ] 34 题 pass 率与分库 4 题 recall 可接受  
- [ ] `learning-log` 填本周生产认知（见模板）  
- [ ] README「当前能力」更新到第 8 周  

---

## 第 9 周预告（开工前读）

| 必做 | 说明 |
|------|------|
| `kb/registry.py` 的 `tool_name` 接到 Agent | `search_policies` / `search_tabular` / `search_pdf_handbook` |
| function calling 选工具 | 用户不选 `--kb`，由 Agent 选 |
| 路由 golden | 单库题必须选对工具；错库对照 |
| Langfuse | span 记 `tool_name`、`kb_id` |

**第 9 周生产认知（预习）**：

1. **Demo**：`--kb` 是运维/调试参数。  
2. **生产**：用户不问库名；**Agent 选工具** ≈ 选库 + 选 Profile。  
3. **升级**：工具稳定后，工具背后可换**物理分库**而不改 Agent 接口。

---

## 每周收尾模板（粘贴到 `learning-log.md`）

```markdown
## YYYY-MM-DD — 第 N 周收尾

### 本周交付（DoD）
- [ ] …

### 本周生产认知（必填 3 条）
1. **Demo 做法**：本项目这周用的简化是什么？
2. **生产常见**：业界一般用什么？（写工具/架构名）
3. **升级触发**：什么规模/失败会逼你换方案？

### Eval / 数字
- pass：…  recall@4：…  对照：…

### 踩坑
- 有 → `rag-pitfalls.md`；无 → 写「本周无新增」

### 下周唯一动作
- 第 N+1 周：…（只写一条，不并行开后期线）
```

---

## 已回填：第 1–8 周生产认知（汇总）

避免「只学了 demo」——每周至少记住下面一行。

| 周 | Demo 做法 | 生产常见 | 升级触发 |
|----|-----------|----------|----------|
| 1 | Chroma 本地文件；标题分块 | pgvector/Qdrant；结构感知分块 | 规模、HA、多租户 |
| 2 | 自建 golden + keyword | + Ragas/人工抽评；Langfuse 或同等 | 线上 bad case 回流 |
| 3 | `bm25.pkl` 全库 `get_scores` | ES/OpenSearch 倒排 | chunk 上万 |
| 4 | 30 题同分 | 更大 golden；分场景集 | 某类题系统性地挂 |
| 5 | 本地 bge-reranker | 可保留本地或 Cohere Rerank API | 延迟/GPU 成本 |
| 6 | CLI + Gradio | API 服务 + 鉴权 + 队列 | 多用户并发 |
| 7 | 全局 `.env` 开关 | 写入各 KB Profile | 已部分完成于 Week 8 |
| 8 | **逻辑分库** + Chroma `where` | **物理分库** + 独立索引；Chroma→Qdrant | 多租户、百万 chunk、不同 embedding |

---

## 后期工程化（不必每周做，按触发条件从 P1/P2 抽）

与 [`production-gap.md` §3](./production-gap.md#3-后期升级改造计划) 对齐：

| 优先级 | 项 | 建议周次或触发 |
|--------|-----|----------------|
| P0 | Agent 路由、路由 eval | 第 9 周 |
| P1 | PDF 管线、噪声过滤、增量 ingest、BM25 倒排 | 真实 PDF / 语料周更 / chunk>5k |
| P2 | 物理分库、换向量库、ES 统一检索、异步 ingest | 上生产、多租户 |

**原则**：主线周（9–12）练「产品与路由」；P1/P2 按 `production-gap` 触发条件插入，不打乱「一周一主题」。

---

## 学习自检（防 demo 陷阱）

每周日 10 分钟，除 plan 里的自检外，加这三问：

1. 我能指出本周代码里**一处故意简化**吗？（查 `production-gap` 易漏讲清单）  
2. 我能说出**生产替代方案的名字**吗？（不是「更好的库」，是 Qdrant/ES/pgvector）  
3. 若明天上线，**最先炸的三件事**是什么？（全量 ingest、单机 BM25、无路由…）

---

## 相关链接

- [详细周计划](../ai-app-engineer-2month-plan.md)  
- [业界差距与改造计划](./production-gap.md)  
- [学习日记](../learning-log.md)  
