# 短 Demo 脚本（约 5 分钟）

用于 Week 6 复盘：展示正常路径 + 一次真实排查过的场景。

## 前置

```bash
uv sync --extra ui --extra dev
cp .env.example .env   # 已配置 OPENAI_API_KEY、Langfuse（可选）
uv run python -m rag_assistant.pipeline --ingest --reset
```

## Part 1：正常问答（1–2 分钟）

**CLI 单轮：**

```bash
uv run python -m rag_assistant.pipeline --query "年假有多少天？怎么折现？"
```

展示点：答案含 `[1]` 引用、底部蓝色「参考来源」块、命中 `02-请假与考勤制度.md`。

**Gradio 多轮：**

```bash
uv run python -m rag_assistant.ui --no-inbrowser
# 浏览器打开 http://127.0.0.1:7860
```

1. 问：「年假有多少天？」
2. 追问：「那病假呢？」→ 右侧应出现 **检索问句** 改写结果

## Part 2：拒答排查（2 分钟）

**库外题（应拒答）：**

```bash
uv run python -m rag_assistant.pipeline --query "公司股票期权怎么行权？"
```

展示点：统一文案「根据现有内部文档，我无法确认。」；若开重排，日志有 `refuse.pre_llm` + `low_confidence`。

**对照 Langfuse（若已配置）：**

- 打开 trace `rag-query`
- 看 `retrieve` 的 top score ≈ 0.06 → `pre_llm_refusal` 未调 generate

## Part 3：Eval 回归（可选 1 分钟）

```bash
uv run python tests/eval/run.py
```

展示点：`pass: 30/30`，结果写入 `data/eval/results/`。

## 脱稿讲解提纲

1. 语料 → 分块 → 向量 + BM25 双索引
2. 问句 →（多轮则改写）→ hybrid 召回 → rerank → 拒答门槛 → 生成 + 引用
3. 用 pitfalls 举例：embed 批大小、HF 下载、eval 关键词误伤、Gradio State
