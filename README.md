# rag-knowledge-assistant

公司内部文档风的 RAG 练习项目：虚构「星云科技」内部知识助手（中文制度 / FAQ / SOP）。

> 学习计划见 [`ai-app-engineer-2month-plan.md`](ai-app-engineer-2month-plan.md)  
> **学习路线图（当前进度 + 12 周全景）**见 [`docs/learning-roadmap.md`](docs/learning-roadmap.md)  
> 从零复现步骤见 [`docs/build-guide.md`](docs/build-guide.md)  
> 方案为何这样选见 [`docs/design-choices.md`](docs/design-choices.md)  
> **与业界落地差距及后期改造计划**见 [`docs/production-gap.md`](docs/production-gap.md)  
> **系统架构**见 [`docs/architecture.md`](docs/architecture.md)  
> **短 Demo 脚本**见 [`docs/demo.md`](docs/demo.md)  
> **面试复习 / 模拟对话**见 [`docs/interview-prep.md`](docs/interview-prep.md)

## 做什么

员工用自然语言问内部问题（年假、报销、权限、发布窗口等）；系统从内部语料 **混合检索 + 重排** 后作答，带引用来源；库外或低置信度问题 **统一拒答**；支持 **多轮追问 + query 改写** 与 **Gradio 界面**。

## 当前能力（第 8 周 · 逻辑分库）

| 能力 | 说明 |
|------|------|
| 语料 | `internal/`（MD/HTML/CSV）+ `kb_pdf/`（PDF 手册） |
| 多库 | KB Registry（policies / tabular / pdf）；**逻辑分库** + `--kb` |
| 入库 | 按 Profile 分块 → Chroma + BM25（`--ingest --reset`） |
| 检索 | hybrid + RRF + rerank；`--kb` 时 metadata **召回阶段下推** |
| 生成 | 强模型 + `[N]` 引用 + 拒答 + 多轮改写 |
| 界面 | CLI `--chat` / Gradio |
| 评测 | golden **34** 题（含 4 道分库专项）；`recall@4`；`score_report` 标定阈值 |

**Eval 基线（hybrid + rerank，主线 30 题）**：pass **30/30**，recall@4 **27/27**。

> Demo vs 生产差距见 [`docs/production-gap.md`](docs/production-gap.md)（Chroma、逻辑分库、BM25 形态等）。

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
