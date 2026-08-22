# 第 11 周：Graph RAG（生产路径）

> **前置**：第 10 周 Qdrant + OpenSearch 已跑通。  
> **本周主题**：关系/多跳问题走 **图检索**，制度条文仍走文档 RAG。  
> **原则**：prose 语料 → 抽取建图 → **Neo4j** → `query_relations`（Cypher），**禁止手写 JSON 图**。

---

## 为什么单独一周

| 问法 | 工具 | 存储 |
|------|------|------|
| 「年假几天」「报销标准」 | `search_policies` | Qdrant + OpenSearch |
| 「周凯上级是谁」「订单服务依赖什么」「报销审批链」 | `query_relations` | **Neo4j** |

Graph RAG 不是替代向量检索，而是 **第四条 Agent 工具**，与第 9 周 ReAct 路由模式一致。

---

## 目标架构

```text
制度/架构 prose（MD）+ CSV
    │
    └─► ingest-graph ──► Neo4j（节点 + 边）
              │
              └─► query_relations（Cypher，支持 2-hop）

query 路径不变：文档题 → search_* ；关系题 → query_relations
```

基础设施：与第 10 周共用 `docker-compose.yml`，`docker compose up -d` 已含 Neo4j。

```bash
docker compose ps                    # 确认 neo4j healthy
# Browser: http://localhost:7474     应用: bolt://localhost:7687（见 .env NEO4J_*）
```

`config.py` 已预留 `neo4j_uri` / `neo4j_user` / `neo4j_password`；第 11 周直接写 `ingest-graph` 与 `query_relations` 即可。

---

## 交付清单（DoD）

| # | 交付 | 验收 |
|---|------|------|
| 1 | prose 语料（组织架构、系统依赖、制度里的审批表） | 与通讯录可对齐 |
| 2 | `ingest-graph`：列角色规则 ETL + LLM 补抽 → Neo4j 增量 | 非 JSON 为唯一源 |
| 3 | `query_relations`：Cypher 查询，返回 Observation | 手测 3 道关系题 |
| 4 | Registry 第四库 `relations` + `build_kb_tools` | ReAct 能选用 |
| 5 | 路由 eval：关系题 → `query_relations`；制度题 → `search_policies` | routing 通过 |
| 6 | before/after：无图工具 vs 有图工具（关系题） | `tests/eval/run_graph_compare.py` |

**命令**

```bash
uv sync --extra prod
docker compose up -d
uv run python -m rag_assistant.pipeline --ingest-graph
uv run python -m rag_assistant.pipeline --react --query "周凯的隔级上级是谁？"
uv run python tests/eval/run_routing.py
uv run python tests/eval/run_graph_compare.py
```

## 生产形态（当前实现）

```text
语料 MD/CSV
  ├─ 规则 ETL：表格/有序列表优先，保留确定性结构
  ├─ LLMGraphTransformer 风格抽取：自动识别实体、类型、属性、关系、关系属性和证据
  ├─ 统一 GraphDocument：规则结果与 LLM 结果合并，实体/关系保留来源与置信度
  └─ 按 SourceDoc.file_hash 增量；变更先删该 source 的边再 MERGE
        ▼
     Neo4j
        ▼
问句 → 便宜模型生成通用 GraphPlan（intent/entities/relations/hops）
        → 实体链接（姓名/工号）
        → 仅跑参数化 Cypher 模板（禁止把 LLM 生成的 Cypher 直接执行）
```

LLM 规划失败时用本体词典降级（「上级/依赖/审批链」），**不**把流程名写死成「费用报销」。

### 进度（2026-08-20 验收）

| 项 | 结果 |
|----|------|
| `--ingest-graph` | Person=10 Service=5 Step=4，基础业务边 16；通用 GraphDocument 运行时总边 28 |
| 单测 | **63** passed（`--ignore=tests/eval`；图单测不连 Neo4j） |
| routing | **9/9**（含 3 道关系题 → `query_relations`） |
| golden | 33/34（3 道关系题标 `skip_direct_eval` 不计） |
| ReAct 手测 3 题 | 均选 `query_relations` 且答对 |

**before/after**（`run_graph_compare.py`：文档 hybrid vs Cypher，不调生成）

| 问题 | 文档检索命中 | 图检索 |
|------|-------------|--------|
| 周凯的隔级上级是谁？ | 0（rerank 滤空） | 周凯 → 何北 → **苏晚** |
| 订单服务间接依赖哪些服务？ | 0 | 含 2 跳 **账户服务** |
| 报销审批链有哪些环节？ | 1（弱相关） | 四环含 **林舒 / 苏晚** |

---

## 明确不做（本周）

- Microsoft GraphRAG 全量社区摘要（规模过大，知道即可）
- 与第 10 周抢工：不回退 Chroma、不并行改 OpenSearch

---

## 与第 12 周关系

| 周 | 主题 |
|----|------|
| 第 10 周 | 生产存储（Qdrant + OpenSearch）已验收 |
| **第 11 周** | **本文档（Graph RAG）已验收** |
| 第 12 周 | 多模态 + CRAG + 12 周总复盘 ← 下一步 |

---

## 相关文档

- [系统架构](./architecture.md) — 四个工具与模块职责
- [入库流水线](./ingest-pipeline.md) — 文档链路（图链路见本文）
- [问答流水线](./query-pipeline.md) — 「图检索分支」一节
- [第 10 周存储改造](./production-upgrade.md)
- [demo vs 生产](./production-gap.md) — §2.9 关系检索对照
- [12 周总计划](../ai-app-engineer-2month-plan.md)
