# Learning Log

## 2026-07-25 — Week 1 开始

- 目标：跑通最简 RAG baseline（ingest → retrieve → generate）
- 决策：语料先用已有的 FastAPI markdown 英文文档；向量库 Chroma；模型走 DashScope OpenAI 兼容接口
- 卡点：首次 `--ingest` 失败——`.env` 里 `OPENAI_API_KEY` 为空（有 key 名、无值）；Langfuse 等其它项已填
- 决策变更：语料改为「公司内部文档风」——虚构星云科技中文制度/FAQ/SOP（`data/corpus/internal/`）；英文 FastAPI 文档不再作为默认
- 决策变更：不做「先错后对」——分块直接按标题；加载 MD/HTML/CSV；LLM 直接带重试与降级
- 下一步：手测几道内部问题；再进可观测 / eval
- 本周异常/失败：（记到 `rag-pitfalls.md`）

## 2026-07-26 — Week 1 手测收尾 → Week 2 开始

- Week 1 手测：年假、生产权限、差旅住宿、发布窗口、L3/L4、会议室/打印机、工号 XY003、入职 Day1、库外期权拒答——均可接受；无新 pitfalls
- Week 2 目标：看见内部 + 最小可靠性 + 第一套 Eval
- 已具备：`llm.py` 超时 / 可重试错误区分 / 强→弱降级（Week 1 已做对，本周不重写）
- 本周开工：
  1. Langfuse：`observability.py` + `query`/`generate` 打 span（retriever + generation）
  2. golden set：`data/eval/golden.json`（15 题，含手测与 2 道拒答）
  3. 最简评分：`uv run python tests/eval/run.py`
- 决策：评分先用 `must_contain` 关键词命中，不急上 ragas；先建立可重复 baseline
- 首轮 baseline：`14/15` pass，`avg_keyword_score=0.967`（结果在 `data/eval/results/`）
- 唯一 FAIL（sec-l3l4）是评分误伤：答案用「禁止」未命中「不得」——已放宽关键词；说明关键词评分脆，不是检索/生成错了
- 请到 Langfuse 控制台确认能看到 `rag-query` → `retrieve` / `generate` 的 trace

## 2026-07-26 — Week 3：混合检索

- 决策：向量 + BM25，用 RRF 融合（不先做加权，避免两路分数量纲问题）
- 实现：`retrieval/bm25.py`、`retrieval/hybrid.py`；ingest 同步写 `bm25.pkl`；默认 `--retrieve hybrid`
- 对照：`--retrieve vector` 可切回纯向量
- 踩坑：整批 57 条 embed 被网关限 ≤20（记入 pitfalls）；改为分批
- eval：hybrid 下 `15/15`（`data/eval/results/hybrid_*.json`）；相对 Week2 向量 baseline 的 14/15，关键词误伤那题也过了（模型这次用了「禁止」）
- 说明：本批题原先向量已经较强，混合检索的收益主要在「工号/专有名词」稳定性；分数满分不能过度解读为「巨大提升」
- 下一步（可选）：重排 / PDF loader；或先用 `--retrieve vector` 再跑一遍 eval 做 before/after

## 2026-07-27 — Week 3：重排（rerank）

- 决策：召回多取候选（≥12）→ `bge-reranker-base` cross-encoder 精排 → 截断 top-k
- 实现：`retrieval/rerank.py`；pipeline `--rerank` / `--no-rerank`；默认 `RERANK_ENABLED=true`
- 踩坑：HuggingFace 下载卡住/不完整；改用 ModelScope `snapshot_download('BAAI/bge-reranker-base')`，代码优先读本地 ModelScope 缓存
- 手测：问 XY003，重排后通讯录 top1 score≈0.999，答案正确
- eval：`hybrid+rerank` → 14/15（0.933）；对比此前 hybrid 无重排 15/15——本批题未体现明显增益，且有 1 题掉点（记结果，不硬吹变好）
- 下一步按序：进入 **第 4 周**（扩题 + recall@k + 三路对照）；PDF / 工具路由留给后期

## 2026-07-28 — 节奏约定：先主线、后加深

- 用户反馈：前三周节奏收获大，希望**循序渐进**；原先 1–6 周练完并掌握后，再练分库/工具路由/多场景
- 约定：第 7–12 周只作主线之后的加深路线图；**当前唯一执行面 = 第 4 周 → 5 → 6**
- 后期仍保留「多 KB = 多策略 = 多工具 + Agent 路由」目标，但不与主线并行
- **下一步**：执行第 4 周；不提前做第 9–12 周

## 2026-07-28 — Week 4 进行中

- Step1：golden 扩至 30 题；评分支持同义组 + 去空格比对
- Step2：`expected_sources` + `recall@k`（检索侧）；`pipeline.retrieve_chunks` 供 eval 与生成共用同一检索
- Step3：`eval_compare` 一键三路对照（vector / hybrid / hybrid+rerank）
- 待你本地跑：`uv run python tests/eval/compare.py`（可先 `--limit 3` 试跑）
- 目录整理：eval 脚本迁至 `tests/eval/`（与主流程 `src/rag_assistant/` 分离）

## 2026-07-29 — Week 4 收尾：全量三路对照

- 全量跑通：`uv run python tests/eval/compare.py`（30 题 × 3 路，无 `--limit`）
- 对照结果（`data/eval/results/compare_latest.json`）：

  | 配置 | pass | keyword | recall@4 |
  |------|------|---------|----------|
  | vector_norerank | 30/30 | 1.0 | 27/27 |
  | hybrid_norerank | 30/30 | 1.0 | 27/27 |
  | hybrid_rerank | 30/30 | 1.0 | 27/27 |

  明细：`vector_norerank_20260729_001714.json` / `hybrid_norerank_20260729_001952.json` / `hybrid_rerank_20260729_002244.json`

- recall 分母 27：3 道库外拒答题（如 `oop-headcount`）无 `expected_sources`，不计入 recall
- 三路同分 → **本 golden set 未能区分检索方案优劣**；不据此宣称 hybrid/rerank「无效」，只说明当前 30 题 + 57 chunks 语料下，纯向量已够用，或生成侧能弥补检索差异
- 与 Week 3 对比：15 题时 hybrid+rerank 曾 14/15；扩题至 30 + 同义组评分后三路均满分——baseline 更稳，但不代表生产全覆盖
- **默认配置决策**：保持 **hybrid + rerank**（`RERANK_ENABLED=true`，与代码默认一致）
  - 理由：本批无回归；历史上工号/专名类题 hybrid 更稳；代价是 BM25 + rerank 额外延迟
  - 若后续只在意速度，可切 `hybrid` 无重排再跑一轮对照验证
- eval 文档：`tests/eval/README.md`（口述版 + 术语对照 + 结果阅读指南）已提交
- 本周未新增 pitfalls（无 FAIL 题、无分数掉点需排查）
- **Week 4 DoD 达成**：扩题 + recall@k + 三路一键对照 + 基线留档
- **下一步**：第 5 周——来源引用、拒答固化、多轮 + query 改写、最小界面（Gradio/API）；不提前做多 KB / Agent 路由

## 2026-07-29 — Week 5 开始：来源引用

- 目标：答案可追溯，排查时能一眼看到「引了哪条、检索还命中了哪些 chunk」
- 实现：
  - `generation.py`：`Citation` 结构体；`build_citations()` 解析正文 `[N]`；`format_sources_block()` 输出参考来源块（文件名 + 已引用/检索命中 + score + 片段预览）
  - `pipeline.py`：`QueryResult`（answer / chunks / citations）；CLI `--query` 先打正文再打蓝色来源块；Langfuse trace 写入 `citations`
  - prompt 调整：正文内联 `[N]`，来源列表由程序追加（避免模型重复罗列或漏列）
- eval 仍只对 `generate()` 正文打分，来源块不参与 keyword 评分
- 单测：`tests/test_citations.py`
- **下一步**：拒答策略固化（Week 5 第 2 项）

## 2026-07-29 — Week 5：拒答策略固化

- 目标：库外 / 低相关问题时稳定拒答，产品与 eval 用同一套规则
- 实现：
  - `refusal.py`：`REFUSAL_MESSAGE` 唯一文案；`is_refusal()`；`pre_llm_refusal()` 生成前检查
  - **低置信度拒答**：重排启用时 top-1 score < `REFUSE_MIN_RERANK_SCORE`（默认 0.15）→ 不调 LLM，直接拒答（如库外题 rerank≈0.06）
  - 混合检索无重排时 RRF 分数不可比，跳过 score 门槛，仍靠 prompt + 模型拒答
  - `produce_answer()`：`query` 与 eval 共用；`QueryResult` 增加 `refused` / `refusal_reason`；CLI 黄色提示拒答原因
  - eval `scoring.py` 改用 `is_refusal()`，与产品侧一致
- 配置：`.env.example` 增加 `REFUSE_MIN_RERANK_SCORE` / `REFUSE_MIN_VECTOR_SCORE`
- 单测：`tests/test_refusal.py`
- **下一步**：多轮 + query 改写（Week 5 第 3 项）

## 2026-07-30 — Week 5：多轮 + query 改写

- 目标：追问带指代时，先结合历史改写成独立检索问句，再 hybrid+rerank 检索
- 实现：
  - `conversation.py`：`ChatTurn`、历史裁剪（最近 6 条）、`format_history`
  - `query_rewrite.py`：`rewrite_for_retrieval()`（cheap 模型）；无历史则跳过 LLM
  - `pipeline.py`：`query(history=...)` 检索/生成均用改写后问句；`QueryResult.rewritten_query`；`--chat` 交互多轮
  - Langfuse：`query-rewrite` span；`rag-query` 记录 `rewritten_query`
- 手测：`uv run python -m rag_assistant.pipeline --chat`，先问年假再问「那病假呢？」，应显示检索问句并答对
- 单测：`tests/test_query_rewrite.py`
- **下一步**：最小界面 Gradio/API（Week 5 第 4 项）

## 2026-07-30 — Week 5：Gradio 最小界面

- 目标：本地可演示的多轮助手，能看答案、检索问句与命中 chunk
- 实现：
  - `ui.py`：Gradio Blocks；左侧对话、右侧「检索详情」；复用 `query(history=...)`
  - 依赖：`uv pip install -e ".[ui]"`（`gradio>=5`）
  - 启动：`uv run python -m rag_assistant.ui`（`--port` / `--share`）
- 单测：`tests/test_ui.py`（格式化逻辑，不启 Web）
- **Week 5 DoD 达成**：引用、拒答、多轮改写、最小界面
- **下一步**：第 6 周复盘（pitfalls、架构图、README、demo）
