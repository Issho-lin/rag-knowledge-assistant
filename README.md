# rag-knowledge-assistant

公司内部文档风的 RAG 练习项目：虚构「星云科技」内部知识助手（中文制度 / FAQ / SOP）。

## 文档导航（迷路只看这 3 个）

| 优先级 | 文档 | 什么时候看 |
|--------|------|------------|
| **1** | [`docs/week11-graph-rag.md`](docs/week11-graph-rag.md) | **第 11 周（当前）**：Graph RAG（Neo4j） |
| **1b** | [`docs/production-upgrade.md`](docs/production-upgrade.md) | 第 10 周已验收：Qdrant + OpenSearch |
| **2** | [`docs/production-gap.md`](docs/production-gap.md) §1 | demo vs 生产对照 |
| **3** | 本文 README | 跑起来、命令、目录结构 |

架构细节：[`docs/architecture.md`](docs/architecture.md)

**参考资料**（需要时再查，不必通读）：

- [`ai-app-engineer-2month-plan.md`](ai-app-engineer-2month-plan.md) — 12 周周计划细项
- [`docs/design-choices.md`](docs/design-choices.md) — 历史选型原因
- [`docs/ingest-pipeline.md`](docs/ingest-pipeline.md) / [`docs/query-pipeline.md`](docs/query-pipeline.md) — 流水线细节
- [`docs/interview-prep.md`](docs/interview-prep.md) — 面试口述
- [`rag-pitfalls.md`](rag-pitfalls.md) — 踩坑实录

## 做什么

员工用自然语言问内部问题；系统从多库语料 **混合检索 + 重排** 后作答，带引用；低置信度 **拒答**；支持 **多轮改写**、**Agent 工具路由** 与 **ReAct**。

## 当前：第 10 周已验收（生产存储）

| 能力 | 说明 |
|------|------|
| 语料 | `internal/`（MD/HTML/CSV）+ `kb_pdf/`（PDF）；约 14 篇 → 72 chunk |
| 多库 | KB Registry（policies / tabular / pdf）；**物理分库** + Profile |
| 入库 | 默认 `--ingest` 增量（`doc_id` + `file_hash`）；`--reset` 全量 |
| 检索 | hybrid + RRF + rerank；生产 Qdrant + OpenSearch，CI 用 Chroma + pkl |
| 问答路径 | `--query` 直连 · `--agent` 路由单库 · **`--react` ReAct（主路径）** |
| 界面 | CLI `--chat --react`；Gradio（ReAct） |

## 布局

```
src/rag_assistant/
  cli.py, ui.py
  core/          # 配置、日志、LLM
  ingest/        # 入库
  kb/            # 注册表、Profile、search 工具
  retrieval/     # 向量、BM25、hybrid、rerank、engine
  answer/        # generate、refusal
  query/         # retrieve、preprocess、modes（direct / agent_route / agent_react）
tests/eval/      # golden、routing、compare
data/corpus/     # 语料（源文档）
data/chroma/     # Chroma 索引（VECTOR_BACKEND=chroma 时，不进 Git）
docs/
```

## 快速开始

### 生产模式（Qdrant + 全栈基础设施）

```bash
docker compose up -d   # Qdrant + OpenSearch + Neo4j（后两者第 10/11 周再接代码）
cp .env.example .env   # OPENAI_API_KEY；VECTOR_BACKEND=qdrant
uv sync --extra dev --extra ui --extra prod
uv run python -m rag_assistant.pipeline --ingest --reset   # 首次全量；之后只需 --ingest
uv run python -m rag_assistant.pipeline --react --query "年假有多少天？"
```

### 离线 / CI 模式（Chroma，默认）

```bash
uv venv --python 3.11
uv sync --extra dev --extra ui
cp .env.example .env   # OPENAI_API_KEY；VECTOR_BACKEND=chroma（默认）

uv run python -m rag_assistant.pipeline --ingest --reset   # 首次全量；之后只需 --ingest

# 推荐：ReAct
uv run python -m rag_assistant.pipeline --react --query "年假有多少天？怎么折现？"

# 多轮
uv run python -m rag_assistant.pipeline --chat --react

# Web
uv run python -m rag_assistant.ui --no-inbrowser

# 评测
uv run pytest tests/ -q
uv run python tests/eval/run.py
uv run python tests/eval/run_routing.py
uv run python tests/eval/run_react.py
```

重排模型（国内建议 ModelScope 预下载）：

```bash
uv run python -c "from modelscope import snapshot_download; print(snapshot_download('BAAI/bge-reranker-base'))"
```

## 关键决策（简）

- **默认 hybrid + rerank**；rerank 分 + `filter_chunks` 滤空即拒答
- **工具只检索**；ReAct 由 Agent 综合片段写答案
- **存储**：向量 Chroma/Qdrant、BM25 pkl/OpenSearch 可切换；物理分库；默认增量 ingest
- 踩坑实录见 [`rag-pitfalls.md`](rag-pitfalls.md)
