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

## 当前进度快照（2026-08）

| 维度 | 状态 |
|------|------|
| **Git 分支** | `production-storage-upgrade`（自 `week10/relations-graph-kb` 重命名） |
| **最后功能 commit** | 第 9 周 ReAct（`e87dd2d`）；本分支下一 commit = Phase 0–1 基建 |
| **单测** | `41 passed`（默认 `VECTOR_BACKEND=chroma`，CI 无 Docker） |
| **整体完成度** | 第 10 周约 **30%**（5 个 Phase 中 0 完成、1 代码就绪待验收） |

**已交付（代码 + 文档）**

- `docker-compose.yml`：Qdrant + OpenSearch + Neo4j 全栈
- 向量抽象：`vector_store.py` / `chroma_store.py` / `qdrant_store.py` / `embeddings.py`
- `VECTOR_BACKEND=chroma\|qdrant`；`config` 预留 OpenSearch / Neo4j 连接项
- `docs/production-upgrade.md`、`docs/week11-graph-rag.md`；精简 README；删除学习向旧文档

**仍用 demo 形态**

- 关键词：`bm25.pkl`（Phase 2 换 OpenSearch）
- 分库：逻辑 `where kb=...`（Phase 3）
- 入库：全量 `--reset`（Phase 4）

**你的下一步**：Phase 1 本地验收（见下）→ Phase 2 OpenSearch

---

## Phase 进度（本周只推进一行，不并行）

| Phase | 本周交付 | 替换的 demo | 状态 |
|-------|----------|-------------|------|
| **0** | docker-compose + `.env.example` + 本文档 | — | ✅ |
| **1** | **Qdrant** 向量库（`VECTOR_BACKEND=qdrant`） | Chroma 本地文件 | 🔄 待你本地验收 |
| **2** | **OpenSearch** BM25 | `bm25.pkl` | ⏳ |
| **3** | 物理分库（每 KB 独立 collection / index） | 逻辑分库 `where` | ⏳ |
| **4** | 增量 ingest（`doc_id` + `file_hash`） | 全量 `--reset` | ⏳ |

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

## Phase 2：OpenSearch BM25

- [ ] `BM25_BACKEND=opensearch|pkl` 可切换
- [ ] hybrid RRF 行为不变；`kb` filter 在 OS 查询下推
- [ ] golden / routing eval 仍通过

---

## Phase 3–4

见 [`production-gap.md`](./production-gap.md) §2.3.1（物理分库）、P1-4（增量 ingest）。

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
