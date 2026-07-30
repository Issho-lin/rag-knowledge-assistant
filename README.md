# rag-knowledge-assistant

公司内部文档风的 RAG 练习项目：虚构「星云科技」内部知识助手（中文制度 / FAQ / SOP）。

> 学习计划见 [`ai-app-engineer-2month-plan.md`](ai-app-engineer-2month-plan.md)  
> 从零复现步骤见 [`docs/build-guide.md`](docs/build-guide.md)  
> 方案为何这样选见 [`docs/design-choices.md`](docs/design-choices.md)

## 做什么

员工用自然语言问内部问题，例如年假、报销、权限申请、发布窗口；系统从内部语料检索后作答并标注来源。

当前：中文内部语料（MD / HTML / CSV）+ 按标题分块 + 向量检索。  
后续：混合检索、重排、Eval、可观测。

## 布局

```
src/rag_assistant/     # 主流程：入库、检索、生成
tests/eval/            # 回归评测（golden set，非业务代码）
data/eval/             # golden.json + results/
data/corpus/internal/  # 内部语料（md/html/csv/pdf）
data/chroma/           # 向量索引（本地生成，不进 Git）
docs/build-guide.md    # 复现指南
```

## 快速开始

LLM 使用 **通义千问（DashScope）** OpenAI 兼容接口。

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env   # 填写 OPENAI_API_KEY

# 入库：data/corpus 下全部语料包 → 统一向量库
uv run python -m rag_assistant.pipeline --ingest --reset
# 提问：自动查全部知识，用户无需选库
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"

# 回归评测（golden set，在项目根目录执行）
uv run python tests/eval/run.py
uv run python tests/eval/compare.py --limit 3   # 三路对照，可先小规模试跑

# Web 界面（多轮 + 来源侧栏，需 uv pip install -e ".[ui]"）
uv run python -m rag_assistant.ui
```
