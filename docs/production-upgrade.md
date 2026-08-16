# 第 10 周：生产级存储改造

> **分支**：`production-storage-upgrade`  
> **本周主题**：把 demo 存储（Chroma / `bm25.pkl`）换成 **Qdrant + OpenSearch**，并完成物理分库、增量入库。  
> **本周不做 Graph 业务代码**：关系检索在第 11 周；Neo4j 已在 compose 中就绪。  
> **唯一执行文档**：本文档；Phase 进度只改下面一张表。

**本周不学新 Agent 能力**——ReAct / 三库路由已在第 9 周完成；本周只换「腿」（向量 + 关键词存储与入库）。

---

## 目标架构（本周结束时应达到）

```text
语料 (MD/PDF/CSV)
    │
    └─► ingest ──► Qdrant（向量）
                   OpenSearch（BM25 + filter）
         │
         └─► query ──► hybrid(Qdrant + OpenSearch) → rerank → ReAct（不变）
```

本地：`docker compose up -d`（**Qdrant + OpenSearch + Neo4j** 一次起全栈；Neo4j 第 11 周才写业务代码，但环境可先就绪）

---

## 当前进度快照（2026-08-15）

| 维度 | 状态 |
|------|------|
| **Git 分支** | `production-storage-upgrade` |
| **单测** | 默认 `VECTOR_BACKEND=chroma` + `BM25_BACKEND=pkl`（CI 无 Docker） |
| **整体完成度** | 第 10 周 **5/5 Phase 代码完成**（Qdrant / OpenSearch / 物理分库 / 增量 ingest） |

**已交付**

- `docker-compose.yml`：Qdrant + OpenSearch + Neo4j 全栈
- 向量：`VECTOR_BACKEND=qdrant|chroma`；关键词：`BM25_BACKEND=opensearch|pkl`
- 物理分库：每 KB 独立 collection / index
- 增量入库：`doc_id` + `file_hash`；默认 `--ingest` 跳过未改文件；`--reset` 全量重建

**你的下一步**：本地用 Qdrant + OpenSearch 跑通 ingest / query 后进入第 11 周 Graph RAG

---

## Phase 进度（本周只推进一行，不并行）

| Phase | 本周交付 | 替换的 demo | 状态 |
|-------|----------|-------------|------|
| **0** | docker-compose + `.env.example` + 本文档 | — | ✅ |
| **1** | **Qdrant** 向量库（`VECTOR_BACKEND=qdrant`） | Chroma 本地文件 | ✅ |
| **2** | **OpenSearch** BM25 | `bm25.pkl` | ✅ |
| **3** | 物理分库（每 KB 独立 collection / index） | 逻辑分库 `where` | ✅ |
| **4** | 增量 ingest（`doc_id` + `file_hash`） | 全量 `--reset` | ✅ |

**本周不做**：GraphRAG（→ 第 11 周）、多模态（→ 第 12 周）、CRAG（→ 第 12 周）。

| 周次 | 主题 | 执行文档 |
|------|------|----------|
| **第 10 周** | Qdrant + OpenSearch + 分库 + 增量入库 | **本文档** |
| 第 11 周 | Graph RAG（Neo4j + `query_relations`） | [`week11-graph-rag.md`](./week11-graph-rag.md) |
| 第 12 周 | 多模态 + CRAG + 总复盘 | 总计划第 12 周章节 |

---

## Phase 0：基础设施 ✅

```bash
docker compose up -d
docker compose ps
```

| 服务 | 端口 | 业务接入 | 启动 |
|------|------|----------|------|
| Qdrant | 6333 | Phase 1 | `docker compose up -d` |
| OpenSearch | 9200 | Phase 2 | 同上 |
| Neo4j | 7474 / 7687 | 第 11 周 | 同上（环境先起，代码后接） |

---

## Phase 1：Qdrant（当前动作）

```bash
docker compose up -d
# .env: VECTOR_BACKEND=qdrant
uv run python -m rag_assistant.pipeline --ingest --reset
uv run python -m rag_assistant.pipeline --react --query "年假有多少天？"
uv run pytest tests/ -q --ignore=tests/eval
```

- [x] `VECTOR_BACKEND=qdrant|chroma` 可切换
- [x] ingest / 检索代码已接入
- [ ] **你本地跑通上面四条命令**
- [x] CI 默认 `chroma`（无 Docker 可跑单测）

---

## Phase 2：OpenSearch BM25 ✅

- [x] `BM25_BACKEND=opensearch|pkl` 可切换
- [x] hybrid RRF 行为不变；`kb` filter 在 OS 查询下推
- [x] golden / routing eval 仍通过

---

## Phase 4：增量 ingest ✅

默认 `--ingest` 按文件指纹同步索引，不必每次 `--reset`。

```bash
uv run python -m rag_assistant.pipeline --ingest          # 跳过未改文件
uv run python -m rag_assistant.pipeline --ingest --reset  # 清空后全量
```

- [x] chunk 元数据含 `doc_id` + `file_hash`
- [x] 未改文件不重新 embedding
- [x] 变更文档删除旧 chunk 再写入
- [x] 语料中已消失的文档从向量库 / BM25 删除
- [x] `--only` 只删除该语料包下的失效文档，不误伤其他包
- [x] `--reset` 仍可全量重建

首次从旧索引升级时：没有 `doc_id` 的遗留 chunk 会在增量运行时被清掉，再按当前语料写入。

---

## 本周收尾自检

1. 完成了 Phase 几？（只能填一个数字）
2. `production-gap.md` §1 里哪一行可以从 demo 勾成「已升级」？
3. 能否用一句话说清：**Chroma → Qdrant 改了哪几个文件**？

---

## 相关文档

- [demo vs 生产](./production-gap.md)
- [系统架构](./architecture.md)
- [12 周总计划](../ai-app-engineer-2month-plan.md)
