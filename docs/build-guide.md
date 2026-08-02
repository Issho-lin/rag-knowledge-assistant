# 从零复现：RAG Knowledge Assistant

> **读前须知**：§1–§2 仍可用于搭环境。§3 为 **Week 1 历史骨架**（根目录单文件 `pipeline.py`），与当前 `src/rag_assistant/` 目录结构不一致。  
> **当前架构与模块路径**以 [`architecture.md`](./architecture.md) 为准；克隆本仓库请直接用文末「一键对照」。

---

## 0. 前置条件

- macOS / Linux
- Python **3.11+**
- [uv](https://github.com/astral-sh/uv)
- 通义千问（DashScope）API Key（OpenAI 兼容模式）

---

## 1. 创建项目 / 克隆仓库

**推荐：直接克隆本仓库**（见文末 §一键对照）。

若从空目录手写 Week 1，仅作学习对照，勿与当前代码混用。

---

## 2. 依赖与环境

```bash
uv venv --python 3.11
uv sync --extra dev --extra ui
cp .env.example .env   # 填写 OPENAI_API_KEY
```

---

## 3. Week 1 历史骨架（已过时，仅存档）

早期版本在包根目录放置 `config.py`、`generation.py`、`pipeline.py`（含 `ingest` / `query`）。  
当前已拆为：

| 旧路径 | 现路径 |
|--------|--------|
| `config.py` | `core/config.py` |
| `generation.py` | `answer/generate.py` |
| `refusal` | `answer/refusal.py` |
| `pipeline.query` | `query/modes/direct.py` |
| `pipeline.ingest` | `ingest/run.py` |
| CLI | `cli.py`；`pipeline.py` 仅为 `main` 别名 |

数据流（概念不变）：

```
语料 → load → Profile 分块 → embed → Chroma + BM25
用户问题 → 检索 → 生成（或 ReAct Agent）
```

---

## 4. 语料与入库

```bash
uv run python -m rag_assistant.pipeline --ingest --reset
```

语料：`data/corpus/internal/`、`data/corpus/kb_pdf/` 等。索引：`data/chroma/unified/`。

详见 [ingest-pipeline.md](./ingest-pipeline.md)。

---

## 5. 提问

```bash
# 直连 RAG（评测基线）
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"

# ReAct（推荐演示 / 生产路径）
uv run python -m rag_assistant.pipeline --react --query "工号 XY003 是谁？"

# Agent 路由（对照）
uv run python -m rag_assistant.pipeline --agent --query "工号 XY003 是谁？"
```

详见 [query-pipeline.md](./query-pipeline.md)。

---

## 6. 评测

```bash
uv run pytest tests/ -q
uv run python tests/eval/run.py
uv run python tests/eval/run_routing.py
```

---

## 7. 辅助文档

| 文件 | 作用 |
|------|------|
| [architecture.md](./architecture.md) | **当前**模块与三条问答路径 |
| [learning-roadmap.md](./learning-roadmap.md) | 12 周进度 |
| [design-choices.md](./design-choices.md) | 方案取舍 |
| [production-gap.md](./production-gap.md) | 与业界差距 |
| `learning-log.md` / `rag-pitfalls.md` | 日记与踩坑 |

---

## 一键对照：克隆本仓库到跑通

```bash
cd rag-knowledge-assistant
uv venv --python 3.11
uv sync --extra dev --extra ui
cp .env.example .env
# 编辑 .env：OPENAI_API_KEY；可选配置 Langfuse

uv run python -m rag_assistant.pipeline --ingest --reset
uv run python -m rag_assistant.pipeline --react --query "年假有多少天？怎么折现？"
uv run pytest tests/ -q
```
