# 系统架构（按当前实现）

> 对应代码：`src/rag_assistant/` · 默认配置：**hybrid + rerank**  
> 入口：`python -m rag_assistant.pipeline` → `cli.main()`（`pipeline.py` 仅为别名）

## 目录结构（问答相关）

```
src/rag_assistant/
├── cli.py                 # argparse：--ingest / --query / --agent / --react / --chat
├── pipeline.py            # → cli.main
├── ui.py                  # Gradio（query_agent_react）
├── core/                  # config, logging, llm, paths, observability
├── ingest/run.py          # 入库流水线
├── kb/                    # registry, profiles, search（工具 + run_kb_retrieve）
├── retrieval/             # vector, bm25, hybrid, rerank, engine, filters, context
├── answer/                # generate（produce_answer）, refusal
└── query/
    ├── retrieve.py        # retrieve_chunks 入口
    ├── result.py          # QueryResult
    ├── preprocess/        # rewrite, decompose
    └── modes/
        ├── direct.py      # --query（全库 / --kb）
        ├── agent_route/   # --agent（路由选 1 库 + produce_answer）
        └── agent_react/   # --react（ReAct 多工具，工具只返回片段）
```

## 端到端总览

> 入库见 [ingest-pipeline.md](./ingest-pipeline.md)。  
> 问答三条路径见 [query-pipeline.md](./query-pipeline.md)。  
> Chunk 结构见 [chunk-data-model.md](./chunk-data-model.md)。

```mermaid
flowchart TB
    subgraph ingest["入库（离线）"]
        A1[语料 MD/HTML/CSV/PDF] --> A2[ingest: loaders + Profile 分块]
        A2 --> A3[Embedding 分批≤20]
        A3 --> A4[(Chroma unified)]
        A2 --> A5[(BM25 pkl)]
    end

    subgraph shared["共享：检索层"]
        SQ[检索问句 search_q] --> RET[retrieve_with_options]
        RET --> OUTC[top-k chunks]
    end

    subgraph modes["问答（三选一）"]
        M1["--query direct.query<br/>全库或 --kb"] --> RET
        M2["--agent query_agent<br/>路由 1 库"] --> RET
        M3["--react 工具 run_kb_retrieve<br/>可多库多调"] --> RET
        OUTC --> PA[produce_answer]
        PA --> QR1[QueryResult]
        OUTC --> OBS[片段 Observation]
        OBS --> AG[ReAct LLM 写答案]
        AG --> QR2[QueryResult]
    end

    subgraph surface["入口"]
        CLI["cli / pipeline"]
        UI[ui.py]
        EV[tests/eval/run.py]
    end

    CLI --> M1 & M2 & M3
    UI --> M3
```

## 三条问答路径

| CLI | 代码入口 | 谁选库 | 谁生成最终答案 |
|-----|----------|--------|----------------|
| `--query` | `query/modes/direct.py` | 用户不选（全库）或 `--kb` | `produce_answer` |
| `--agent` | `query/modes/agent_route/` | cheap LLM function calling 选 **1** 个工具 | `produce_answer` |
| `--react` | `query/modes/agent_react/` | Agent 循环调工具，可 **多个** KB | Agent 读 Observation 后撰写 |

**工具统一约定**（`kb/search.py`）：`build_kb_tools()` 只检索，返回格式化片段；不在工具内调用 `produce_answer`。

## 模块职责

| 模块 | 职责 |
|------|------|
| `ingest/` | 语料发现、按 Profile 切块、写 Chroma + BM25 |
| `kb/registry.py` | 逻辑 KB（policies / tabular / pdf）与 tool 名 |
| `kb/profiles.py` | 每库切块 + 检索增强开关（decompose、expand_parent） |
| `kb/search.py` | `run_kb_retrieve`、LangChain 工具、`format_chunks_observation` |
| `retrieval/engine.py` | 子查询分解、召回、rerank、过滤、父文档扩展 |
| `query/preprocess/rewrite.py` | 多轮指代补全（有历史才改写） |
| `query/preprocess/decompose.py` | 可选子查询分解（单库内，默认关） |
| `answer/refusal.py` | 拒答文案 + `pre_llm_refusal` / `is_refusal` |
| `answer/generate.py` | `produce_answer`、`build_citations` |
| `retrieval/rerank.py` | bge-reranker；`RLock` 串行化（ReAct 并行 tool 时防 MPS 崩溃） |
| `cli.py` | 命令行入口 |
| `tests/eval/` | golden 回归、路由 eval、三路检索对照 |

## 观测点（Langfuse）

**`--query` / `--agent`：**

```
rag-query / rag-agent-query
├── query-rewrite（仅多轮）
├── retrieve 或 agent-route
└── generate（produce_answer 内）
```

**`--react`：**

```
rag-react-query
└── agent-react（工具内检索无单独 produce_answer span）
```

## Eval 基线（2026-08-02）

| 套件 | 指标 |
|------|------|
| `tests/eval/run.py`（检索 + produce_answer） | golden **34/34**，recall@4 **31/31** |
| `tests/eval/run_routing.py`（`--agent` 选型） | routing **6/6** |
| 单测 | **44** passed |

三路检索对照（vector / hybrid / hybrid+rerank）：`tests/eval/compare.py`。

## 关键配置（`.env`）

- `RERANK_ENABLED=true` — 默认开重排
- `REFUSE_MIN_RERANK_SCORE=0.15` — rerank 后低分过滤阈值（滤空 → 拒答）
- `QUERY_DECOMPOSE_ENABLED=false` — 子查询分解（默认关；ReAct 复合题主要靠 Agent 拆 tool query）
- `CHAT_MODEL_STRONG` / `CHAT_MODEL_CHEAP` — 生成 / 改写 / 路由分级

## 相关文档

- [问答流水线](./query-pipeline.md)
- [与业界落地差距](./production-gap.md)
