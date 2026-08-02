# 短 Demo 脚本（约 8 分钟）

展示：直连 RAG、ReAct 复合题、拒答与回归。

## 前置

```bash
uv sync --extra ui --extra dev
cp .env.example .env   # OPENAI_API_KEY；Langfuse 可选
uv run python -m rag_assistant.pipeline --ingest --reset
```

## Part 1：直连 RAG（1 分钟）

```bash
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"
```

展示点：`[1]` 引用、蓝色「参考来源」、命中制度 MD。

## Part 2：ReAct 复合题（2–3 分钟，推荐生产路径）

```bash
uv run python -m rag_assistant.pipeline --react --query "XY003 的报销额度是多少？另外打印机卡纸怎么处理？"
```

展示点：日志 `agent.react_done` 多次 tool；引用可来自 CSV + PDF + 制度；对比 `--agent` 同题易单库拒答。

单库对照：

```bash
uv run python -m rag_assistant.pipeline --react --query "工号 XY003 是谁？"
```

## Part 3：多轮（1 分钟）

**CLI：**

```bash
uv run python -m rag_assistant.pipeline --chat --react
```

**Gradio**（ReAct，与 CLI `--chat --react` 一致）：

```bash
uv sync --extra ui
uv run python -m rag_assistant.ui --no-inbrowser
```

## Part 4：拒答（1 分钟）

```bash
uv run python -m rag_assistant.pipeline --query "公司股票期权怎么行权？"
```

展示点：「根据现有内部文档，我无法确认」；日志 `refuse.pre_llm`。

## Part 5：Eval（1 分钟）

```bash
uv run python tests/eval/run.py
uv run python tests/eval/run_routing.py
uv run python tests/eval/run_react.py
```

展示点：golden **34/34**；routing **6/6**；ReAct **6/7**。

## 脱稿提纲

1. 入库：Profile 分块 → Chroma + BM25  
2. 检索共享层：hybrid → rerank → 低分过滤  
3. **ReAct**：工具只返回片段 → Agent 写答案（生产默认）  
4. `--query` / `--agent`：评测与对照，不是用户必选  
5. 踩坑见 `rag-pitfalls.md`（embed 批大小、HF 镜像、ReAct 并行 rerank）
