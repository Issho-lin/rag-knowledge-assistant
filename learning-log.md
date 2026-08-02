# Learning Log

> **全局路线图**：[`docs/learning-roadmap.md`](docs/learning-roadmap.md)（当前指针、12 周全景、每周 DoD）  
> **Demo vs 生产**：[`docs/production-gap.md`](docs/production-gap.md)（易漏讲清单、逻辑/物理分库、Chroma 选型）  
> **详细周计划**：[`ai-app-engineer-2month-plan.md`](ai-app-engineer-2month-plan.md)

---

## 每周收尾模板（含生产认知）

每周日或完成该周 DoD 时，复制一段到下方追加：

```markdown
## YYYY-MM-DD — 第 N 周收尾

### 本周交付（DoD）
- [ ] …

### 本周生产认知（必填 3 条）
1. **Demo 做法**：…
2. **生产常见**：…（写工具/架构名）
3. **升级触发**：…

### Eval / 数字
- …

### 踩坑
- …

### 下周唯一动作
- …
```

---

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
- 待你本地跑：`uv run python tests/eval/compare.py`（可先加 `--limit 3` 试跑）
- 目录整理：eval 脚本迁至 `tests/eval/`（与主流程 `src/rag_assistant` 分离）

## 2026-07-29 — Week 4 收尾：全量三路对照

- 全量跑通：`uv run python tests/eval/compare.py`（30 题 × 3 路，无 `--limit`）
- 对照结果见 `data/eval/results/compare_latest.json`：

| 配置 | pass | keyword | recall@4 |
|------|------|---------|----------|
| vector_norerank | 30/30 | 1.0 | 27/27 |
| hybrid_norerank | 30/30 | 1.0 | 27/27 |
| hybrid_rerank | 30/30 | 1.0 | 27/27 |

- 明细：`vector_norerank_20260729_001714.json` / `hybrid_norerank_20260729_001952.json` / `hybrid_rerank_20260729_002244.json`

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

## 2026-07-30 — Week 6：复盘固化

- `rag-pitfalls.md`：补 Week 2 eval 误伤、Week 5 Gradio State、venv 迁移等真实条目
- `docs/architecture.md`：mermaid 端到端架构 + 模块表 + eval 基线
- `docs/demo.md`：5 分钟 demo 脚本（正常问答 + 拒答排查 + eval）
- `README.md`：对齐当前能力、快速开始改 `uv sync`、链到架构与 demo
- `docs/interview-prep.md`：面试模拟对话与口述稿（新功能迭代时同步更新）
- **Week 6 DoD 达成**（待你本地：脱稿讲一遍 + 可选录屏）
- **下一步**：第 7 周及以后（分库 / Profile / Agent 路由）——仅在主线复盘完成后开启

## 2026-07-30 — Week 7：检索增强（过滤 / 子查询 / 父文档）

- 目标：为后续「每库 Profile」准备可插拔能力；本周仍在统一管线上开关验证
- 入库增强：`ChunkInfo` + `parent_text`；Chroma/BM25 写入 `domain` / `kind` / `corpus` 元数据
- 实现：
  - `retrieval/filters.py`：低分过滤 + 元数据过滤（分库预演）
  - `query_decompose.py`：复合问拆子查询 → 多路检索 → RRF 合并
  - `retrieval/context.py`：父文档扩展（子块 → 整节）
  - `retrieval/options.py` + `retrieval/engine.py`：统一编排；`.env` 开关默认全关
- eval：`tests/eval/compare.py --suite enhanced` 五路对照（baseline / filter / decompose / parent / all）
- 决策归属（见 `docs/design-choices.md` §8）：三项默认进 COMMON_PROFILE；通讯录等短块 KB 第 8 周可关 parent_expand
- **必做**：先 `uv run python -m rag_assistant.pipeline --ingest --reset`（写入 parent_text）
- 全量对照：`uv run python tests/eval/compare.py --suite enhanced`（30 题 × 5 路）
- **Week 7 DoD**：三项模块可配 + 对照脚本 + 设计说明
- 拒答/过滤统一：rerank 后按 `REFUSE_MIN_RERANK_SCORE` 滤全部候选，滤空即拒答（去掉 `RETRIEVAL_MIN_SCORE`）
- **下一步**：第 8 周——KB Registry + 多 Profile 分库 + PDF KB

## 2026-08-02 — 第 9 周开工：Agent 工具路由（Step 1）

### 今日完成
- [x] `kb/tools.py`：`run_kb_search` + `build_kb_tools`（每 KB 一个 StructuredTool）
- [x] `agent.py`：`select_tool_names`（cheap 模型 function calling 路由）
- [x] `pipeline.query_agent` + CLI `--agent`（`--query` / `--chat`）
- [x] Langfuse：`rag-agent-query` → `agent-route` span（记 `tool_name` / `kb_id`）
- [x] `tests/eval/run_routing.py` + golden `expected_tool`（6 题路由专项）
- [x] 单测：`tests/test_agent.py`（mock LLM）+ registry 反查

### 本周生产认知（预习 → 已修正）

> 见下方 **「架构决策：ReAct 为主路径」**；早期笔记里「`--agent` 才是产品路径」已作废。

### 明日 / 后续 Step
- [x] 本地跑 `uv run python tests/eval/run_routing.py`（routing **6/6**）
- [x] ReAct 端到端 golden / 复合题手测归档
- [x] `ui.py` 默认切 `query_agent_react`
- [x] `--agent` vs `--react` 对照记入 learning-log（辅助理解，非产品路径）

### 手测
```bash
uv run python -m rag_assistant.pipeline --react --query "工号 XY003 是谁？"
uv run python -m rag_assistant.pipeline --react --query "XY003 的报销额度是多少？另外打印机卡纸怎么处理？"
uv run python tests/eval/run_routing.py
uv run python tests/eval/run.py          # 34/34
uv run python tests/eval/run_react.py    # 6/7
uv sync --extra ui && uv run python -m rag_assistant.ui --no-inbrowser
```

---

## 2026-08-02 — 第 9 周收尾

### DoD 勾选
- [x] 工具层统一：`kb/search.py` 只检索；`--agent` / `--react` 共用 `run_kb_retrieve`
- [x] ReAct 主路径：`query/modes/agent_react/` + CLI `--react` / `--chat --react`
- [x] 路由辅助：`--agent` + `run_routing.py` **6/6**
- [x] ReAct eval：`data/eval/react_golden.json`（7 题）+ `tests/eval/run_react.py` → **6/7**
- [x] Gradio 切 ReAct；侧栏展示 `routed_tool`
- [x] 手测：`run.py` **34/34**、routing **6/6**、复合题 ReAct 可跑完
- [x] 单测 **45** passed（含 `score_react_tools`）

### Eval / 数字
| 套件 | 结果 |
|------|------|
| `run.py` | **34/34**，recall@4 **31/31** |
| `run_routing.py` | **6/6** |
| `run_react.py` | **6/7**（`react_20260802_163630.json`） |
| `pytest` | **45** passed |

**ReAct 唯一 FAIL**：`react-admin-faq`（会议室+打印机复合问）— `tools=T✓`、`recall=R✓`，但 Agent 打印机段落引用 PDF 未写 FAQ 里的 `Xingyun-Office`；属生成选题 + 断言偏严，非链路 bug。已知局限，不阻塞收尾。

### `--agent` vs `--react` 对照（辅助理解）

| 维度 | `--agent` | `--react`（主路径） |
|------|-----------|---------------------|
| 选库 | cheap LLM 一次选 **1** 个工具 | strong Agent 可 **多工具、多轮** |
| 生成 | Python `produce_answer` | Agent 读 Observation 写答案 |
| 复合跨库题 | 易只查一库后拒答 | `react-cross-kb` 双工具通过 |
| 评测 | `run_routing.py` | `run_react.py` |
| 成本/延迟 | 较低 | 较高（多轮 strong LLM + 多检索） |

### 踩坑（本周新增）
- ReAct 并行 tool + MPS rerank → segfault；`rerank.py` **RLock** 串行化（曾用 `Lock` 死锁）
- Gradio 需 `uv sync --extra ui`，否则 `gradio` 无 `Blocks`；`ui.py` 已加友好报错
- `react-admin-faq`：Agent 对「打印机」过度查 PDF，policies 侧 filter 后仅 1 chunk

### 生产认知（第 9 周）
1. **主路径**：CLI / Gradio 默认 **ReAct**；工具只返回片段，Agent 综合写答案。  
2. **评测分层**：`run.py` 测 RAG 底座；`run_routing.py` 测单步路由；`run_react.py` 测 ReAct 端到端（题集小、允许偶发 FAIL）。  
3. **不叠第三层路由**：不必再 LLM 判断 agent vs react。

### 下一步
- **第 10 周**：关系语料 + `query_relations` Tool 挂 Registry，由 ReAct 选用

---

## 2026-08-02 — 架构决策：ReAct 为主路径

> **决策**：生产与学习统一以 **`--react`** 为用户入口；`--query` / `--agent` 仅作辅助——理解 RAG 底座（检索 + `produce_answer`）与单步路由选型，不作为并列产品模式。不必再叠「agent vs react」路由 LLM。

| 路径 | 角色 |
|------|------|
| `--react` | 主流程：多库、复合题、Agent 调工具读片段写答案 |
| `--query` + `tests/eval/run.py` | 辅助：固定检索→生成，测 recall / 拒答 |
| `--agent` + `run_routing.py` | 辅助：cheap 路由评测，理解选库 |
| `--query --kb` | 辅助：单库 Profile 调试 |

**第 10–12 周**：新语料仍走「KB → Profile → Tool → **ReAct 选用**」；图检索 / 多模态 / CRAG 挂在 Tool+Profile 上。

---

### 本周交付（DoD）
- [x] `kb/` Registry + 三 Profile（policies / tabular / pdf）
- [x] 逻辑分库：`kb` 元数据；`--kb`；召回阶段 Chroma `where` + BM25 子集
- [x] PDF 语料（10 办公设备、11 园区后勤）；`load_pdf`；ingest **65 chunks**
- [x] `score_report.py`；golden +4 分库题；`run.py` per-item `kb` / CLI `--kb`
- [x] `docs/production-gap.md`、`docs/learning-roadmap.md`；README 对齐第 8 周
- [x] 验收：`pytest` 11 passed；eval **34/34**，`recall@4` **31/31**

### 本周生产认知（必填 3 条）
1. **Demo 做法**：**逻辑分库**——单 Chroma + 单 `bm25.pkl`，用 `kb` 元数据 + 召回下推过滤；Chroma 本地嵌入式。  
2. **生产常见**：多租户常 **物理分库**（独立 collection/索引）；向量库常用 **pgvector / Qdrant / Milvus**，关键词用 **ES/OpenSearch**；Agent **一工具一库**。  
3. **升级触发**：不能混存 → 物理分库；chunk 上万 → ES 倒排；要 HA/权限 → 换托管向量库；用户不选库 → Week 9 Agent 路由。

### Eval / 数字
- 最终：`hybrid_rerank-default_20260802_003401.json` — pass **34/34**，avg keyword **1.0**，recall@4 **31/31**
- 分库 4 题全过；库外 3 题（`oop-*`）经修 `run.py`（chunks 滤空走 `produce_answer` 拒答）后通过
- 中间态：`...002321.json` 曾 31/34（eval 误报「知识库为空」，非检索回退）

### 踩坑
- eval 与 `pipeline.query` 路径不一致：检索滤空 ≠ 向量库未 ingest
- 文档曾漏讲物理分库、Chroma 非生产默认——已补 `production-gap` + 路线图「生产认知必填」

### 下周唯一动作
- ~~**第 9 周收尾**~~ ✅ 已完成（见上方「第 9 周收尾」）
- **第 10 周**：关系 KB + `query_relations` 挂 Tool
