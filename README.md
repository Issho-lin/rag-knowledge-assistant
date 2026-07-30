# rag-knowledge-assistant

公司内部文档风的 RAG 练习项目：虚构「星云科技」内部知识助手（中文制度 / FAQ / SOP）。

> 学习计划见 [`ai-app-engineer-2month-plan.md`](ai-app-engineer-2month-plan.md)  
> 从零复现步骤见 [`docs/build-guide.md`](docs/build-guide.md)  
> 方案为何这样选见 [`docs/design-choices.md`](docs/design-choices.md)  
> **系统架构**见 [`docs/architecture.md`](docs/architecture.md)  
> **短 Demo 脚本**见 [`docs/demo.md`](docs/demo.md)  
> **面试复习 / 模拟对话**见 [`docs/interview-prep.md`](docs/interview-prep.md)

## 做什么

员工用自然语言问内部问题（年假、报销、权限、发布窗口等）；系统从内部语料 **混合检索 + 重排** 后作答，带引用来源；库外或低置信度问题 **统一拒答**；支持 **多轮追问 + query 改写** 与 **Gradio 界面**。

## 当前能力（第 6 周主线）

| 能力 | 说明 |
|------|------|
| 语料 | 中文 MD / HTML / CSV，`data/corpus/internal/` |
| 入库 | 按标题分块 → Chroma + BM25（`--ingest --reset`） |
| 检索 | 向量 + BM25 → RRF → bge-reranker 重排（默认开启） |
| 生成 | 强模型 + `[N]` 引用 + 程序追加来源块 |
| 拒答 | 低 rerank 分 / 无 chunk → 不调 LLM；eval 与产品共用 `is_refusal()` |
| 多轮 | 有历史时 cheap 模型改写检索问句（`--chat` / Gradio） |
| 可观测 | Langfuse：`rag-query` → `query-rewrite` / `retrieve` / `generate` |
| 评测 | 30 题 golden；`recall@4`；三路对照 `tests/eval/compare.py` |

**Eval 基线（hybrid + rerank，2026-07-30）**：pass **30/30**，recall@4 **27/27**（3 道库外拒答题不计 recall）。

## 布局

```
src/rag_assistant/     # 主流程：入库、检索、生成、拒答、改写、UI
tests/eval/            # 回归评测（golden set）
data/eval/             # golden.json + results/
data/corpus/internal/  # 内部语料
data/chroma/           # 向量索引（本地生成，不进 Git）
docs/                  # build-guide、architecture、demo
rag-pitfalls.md        # 真实踩坑实录
```

## 快速开始

LLM 使用 **通义千问（DashScope）** OpenAI 兼容接口。

```bash
uv venv --python 3.11
uv sync --extra dev --extra ui
cp .env.example .env   # 填写 OPENAI_API_KEY

# 入库
uv run python -m rag_assistant.pipeline --ingest --reset

# 单轮提问
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"

# 多轮 CLI
uv run python -m rag_assistant.pipeline --chat

# Web 界面
uv run python -m rag_assistant.ui --no-inbrowser

# 回归评测
uv run python tests/eval/run.py
uv run python tests/eval/compare.py   # 三路对照 vector / hybrid / hybrid+rerank
```

重排模型需本地缓存（国内建议 ModelScope）：

```bash
uv run python -c "from modelscope import snapshot_download; print(snapshot_download('BAAI/bge-reranker-base'))"
```

## 关键决策（简）

- **默认 hybrid + rerank**：本 golden set 三路同分，但历史上工号/专名类题 hybrid 更稳；代价是延迟
- **无历史不改写**：单轮不额外调 LLM；多轮才 `query_rewrite`（补全指代）
- **RRF 分不做拒答门槛**：只有 rerank 分或纯向量分才触发 `pre_llm_refusal`
- **坑点只记真实的**：见 [`rag-pitfalls.md`](rag-pitfalls.md)
