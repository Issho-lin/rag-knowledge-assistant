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
| 2 | `ingest-graph`：规则 ETL + 可选 LLM 补抽 → **写 Neo4j** | 非 JSON 文件为唯一源 |
| 3 | `query_relations`：Cypher 查询，返回 Observation | 手测 3 道关系题 |
| 4 | Registry 第四库 `relations` + `build_agent_tools` | ReAct 能选用 |
| 5 | 路由 eval：关系题 → `query_relations`；制度题 → `search_policies` | routing 通过 |
| 6 | before/after：无图工具 vs 有图工具（关系题） | 记录对比 |

---

## 明确不做（本周）

- Microsoft GraphRAG 全量社区摘要（规模过大，知道即可）
- 与第 10 周抢工：不回退 Chroma、不并行改 OpenSearch

---

## 与第 12 周关系

| 周 | 主题 |
|----|------|
| 第 10 周 | 生产存储（Qdrant + OpenSearch）← 当前 |
| **第 11 周** | **本文档（Graph RAG）** |
| 第 12 周 | 多模态 + CRAG + 12 周总复盘 |

---

## 相关文档

- [第 10 周存储改造](./production-upgrade.md)
- [demo vs 生产](./production-gap.md)
- [12 周总计划](../ai-app-engineer-2month-plan.md)
