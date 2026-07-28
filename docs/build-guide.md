# 从零复现：RAG Knowledge Assistant

> 目标：按本文顺序操作，得到与当前仓库一致的可运行最简 RAG（Week 1 baseline）。  
> 约定：**只写正确步骤**；不记录排错过程。  
> 应用代码以仓库 `src/rag_assistant/` 下文件为准（创建时按对应路径写入即可）。

---

## 0. 前置条件

- macOS / Linux
- Python **3.11+**
- [uv](https://github.com/astral-sh/uv) 已安装
- 通义千问（DashScope）API Key（OpenAI 兼容模式）
---

## 1. 创建项目

```bash
mkdir rag-knowledge-assistant
cd rag-knowledge-assistant

uv venv --python 3.11
source .venv/bin/activate
```

创建目录：

```bash
mkdir -p src/rag_assistant/ingest src/rag_assistant/retrieval
mkdir -p tests docs
mkdir -p data/corpus/internal/{markdown,html,csv,pdf}
```

---

## 2. 依赖与打包配置

在项目根目录创建 `pyproject.toml`，内容与仓库根目录 [`pyproject.toml`](../pyproject.toml) 一致。

创建 `.gitignore`（与仓库 [`.gitignore`](../.gitignore) 一致）：

```gitignore
.env
.venv/
data/chroma/
data/corpus/markdown/
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
```

创建环境变量模板 `.env.example`（与仓库 [`.env.example`](../.env.example) 一致），然后：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
OPENAI_API_KEY=你的DashScope密钥
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL_STRONG=qwen-max
CHAT_MODEL_CHEAP=qwen-turbo
EMBEDDING_MODEL=text-embedding-v3
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=4
CHROMA_PATH=./data/chroma
CORPUS_DIR=./data/corpus
```

Langfuse 相关项可留空（Week 2 再填）。

安装依赖（可编辑安装）：

```bash
uv pip install -e ".[dev]"
```

---

## 3. 应用代码骨架（Week 1）

按下列路径创建文件，**内容与本仓库同名文件一致**：

| 路径 | 作用 |
|------|------|
| `src/rag_assistant/__init__.py` | 包标识 |
| `src/rag_assistant/config.py` | `pydantic-settings` 读取 `.env` |
| `src/rag_assistant/exceptions.py` | LLM / 应用错误分层 |
| `src/rag_assistant/logging.py` | structlog JSON 日志 |
| `src/rag_assistant/llm.py` | Chat 客户端（OpenAI 兼容） |
| `src/rag_assistant/ingest/__init__.py` | 子包 |
| `src/rag_assistant/ingest/loaders.py` | 加载 Markdown / HTML / CSV → `Document` |
| `src/rag_assistant/ingest/chunking.py` | 按 Markdown 标题分块（过长节再按段落打包） |
| `src/rag_assistant/retrieval/__init__.py` | 子包 |
| `src/rag_assistant/retrieval/vector.py` | Embedding + Chroma；`check_embedding_ctx_length=False`（兼容国内 embedding 网关） |
| `src/rag_assistant/generation.py` | 基于检索片段生成带引用答案 |
| `src/rag_assistant/pipeline.py` | CLI：`--ingest` / `--query` |
| `tests/test_config.py` | 不依赖真密钥的单元测试 |

数据流：

```
语料(MD/HTML/CSV) → load → 按标题分块 → embed → Chroma
用户问题 → embed → top-k 检索 → prompt + LLM → 答案
```

验证导入：

```bash
uv run python -c "from rag_assistant.pipeline import ingest, query; print('ok')"
```

跑单元测试（可选）：

```bash
uv run pytest -q
```

---

## 4. 准备语料（公司内部文档风 · 中文）

产品定位：**虚构公司「星云科技」的内部知识助手**（制度 / FAQ / SOP / 产品对内说明）。

语料目录（已纳入本仓库，可直接使用）：

```text
data/corpus/internal/
  markdown/   # 制度 / FAQ / SOP（中文 MD）
  html/       # 内部 Wiki 页
  csv/        # 通讯录等表格
  pdf/        # 预留：制度 PDF
  README.md
```

若从空目录手建，将仓库中 `data/corpus/internal/` 整目录拷贝到相同路径即可。

确认语料：

```bash
ls data/corpus/internal/markdown/*.md
ls data/corpus/internal/html data/corpus/internal/csv
```

知识组织在 `data/corpus/<任意名>/{markdown,html,csv}/`。  
`ingest` 会把**所有语料包**打进统一向量库；用户提问**不选库**，自动查全部：

```bash
uv run python -m rag_assistant.pipeline --ingest --reset
uv run python -m rag_assistant.pipeline --query "年假怎么算"
```

新增知识：新建或往已有子目录加文件 → 再执行一次 `--ingest --reset`。  
统一向量库路径：`data/chroma/unified/`。

---

## 5. 建索引（Ingest）

确保 `.env` 中 `OPENAI_API_KEY` 已填写且非空，然后：

```bash
# 首次或更换语料后建议加 --reset，清空旧索引再重建
uv run python -m rag_assistant.pipeline --ingest --reset
```

成功时终端会打印类似：

```text
已从 data/corpus/internal 索引 <N> 个 chunk。
```

索引落在 `data/chroma/`（本地持久化）。

---

## 6. 提问（Query）

```bash
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"
```

其它示例：

```bash
uv run python -m rag_assistant.pipeline --query "生产环境权限怎么申请？"
uv run python -m rag_assistant.pipeline --query "差旅住宿标准是多少？" --k 4
```

预期：先打印检索到的 chunk 预览，再打印 `A:`；答案为中文，并带 `[1]`、`[2]` 来源编号。

---

## 7. 辅助文档（本仓库学习用，复现主流程可不建）

| 文件 | 作用 |
|------|------|
| `ai-app-engineer-2month-plan.md` | 学习计划 |
| `learning-log.md` | 个人学习记录 |
| `rag-pitfalls.md` | 真实踩坑实录（事后记） |
| `docs/build-guide.md` | 本文：正确操作步骤 |

---

## 进度（随项目推进追加章节）

| 阶段 | 状态 | 对应章节 |
|------|------|----------|
| Week 1：最简 RAG baseline（内部中文语料） | 已跑通 ingest + 中文 query | §1–§6 |
| Week 2：可观测 + 可靠性 + 最小 Eval | 未开始 | 待追加 |
| Week 3：检索质量工程 | 未开始 | 待追加 |
| Week 4：Eval 回归 | 未开始 | 待追加 |
| Week 5：引用 / 多轮 / 界面 | 未开始 | 待追加 |
| Week 6：复盘固化 | 未开始 | 待追加 |

---

## 一键对照：当前仓库从克隆到跑通

若直接使用本仓库（而不是从空目录手写代码）：

```bash
cd rag-knowledge-assistant
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

uv run python -m rag_assistant.pipeline --ingest --reset
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"
```
