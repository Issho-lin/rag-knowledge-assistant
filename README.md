# rag-knowledge-assistant

公司内部文档风的 RAG 练习项目：虚构「星云科技」内部知识助手（中文制度 / FAQ / SOP）。

> 学习计划见 [`ai-app-engineer-2month-plan.md`](ai-app-engineer-2month-plan.md)  
> **学习路线图**见 [`docs/learning-roadmap.md`](docs/learning-roadmap.md)  
> 从零复现见 [`docs/build-guide.md`](docs/build-guide.md)  
> 方案为何这样选见 [`docs/design-choices.md`](docs/design-choices.md)  
> **与业界落地差距**见 [`docs/production-gap.md`](docs/production-gap.md)  
> **系统架构**见 [`docs/architecture.md`](docs/architecture.md)  
> **短 Demo 脚本**见 [`docs/demo.md`](docs/demo.md)  
> **面试复习**见 [`docs/interview-prep.md`](docs/interview-prep.md)

## 做什么

员工用自然语言问内部问题；系统从多库语料 **混合检索 + 重排** 后作答，带引用；低置信度 **拒答**；支持 **多轮改写**、**Agent 工具路由** 与 **ReAct**。

## 当前能力（第 9 周 · Agent + ReAct）

| 能力 | 说明 |
|------|------|
| 语料 | `internal/`（MD/HTML/CSV）+ `kb_pdf/`（PDF） |
| 多库 | KB Registry（policies / tabular / pdf）；逻辑分库 + Profile |
| 入库 | 按 Profile 分块 → 统一 Chroma + BM25（`--ingest --reset`） |
| 检索 | hybrid + RRF + rerank；KB 过滤在召回阶段下推 |
| 问答路径 | `--query` 直连 · `--agent` 路由单库 · **`--react` ReAct（推荐演示/生产）** |
| 工具 | 每 KB 一个 `search_*`，**只返回检索片段**；答案由 Agent 或 `produce_answer` 生成 |
| 界面 | CLI `--chat --react`；Gradio（ReAct） |
| 评测 | golden **34/34**；routing **6/6**；react **6/7**；单测 **45** |

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
data/corpus/     # 语料
data/chroma/     # 索引（本地，不进 Git）
docs/
```

## 快速开始

```bash
uv venv --python 3.11
uv sync --extra dev --extra ui
cp .env.example .env   # OPENAI_API_KEY

uv run python -m rag_assistant.pipeline --ingest --reset

# 推荐：ReAct
uv run python -m rag_assistant.pipeline --react --query "年假有多少天？怎么折现？"

# 对照：直连 RAG
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"

# 多轮
uv run python -m rag_assistant.pipeline --chat --react

# Web（ReAct 主路径）
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

- **默认 hybrid + rerank**；RRF 分不做拒答门槛，rerank 分 + `filter_chunks` 滤空即拒答
- **工具只检索**；ReAct 由 Agent 综合片段写答案
- **无历史不改写**；多轮才 `rewrite_for_retrieval`
- 踩坑实录见 [`rag-pitfalls.md`](rag-pitfalls.md)
