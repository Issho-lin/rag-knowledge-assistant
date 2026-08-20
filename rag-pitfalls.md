# RAG Pitfalls（过程实录）

> 只记录做的过程中真实撞上的问题。没有就不写。

### LangChain Embedding 默认 tokenize 导致国内网关 400
- 时间/周次：2026-07-25 / Week 1
- 当时在做：对内部中文 MD 语料执行 `--ingest`
- 现象：调用 embeddings 返回 400，`contents is neither str nor list of str`
- 如何发现：终端报错；用官方 `openai` SDK 直接 `input='年假有多少天'` 可成功，说明网关与模型本身可用
- 根因：`langchain_openai.OpenAIEmbeddings` 默认 `check_embedding_ctx_length=True`，会先按 tiktoken 处理再请求；当前 MaaS 的 `qwen3.7-text-embedding` 需要字符串/字符串列表
- 处理：创建 `OpenAIEmbeddings` 时设 `check_embedding_ctx_length=False`
- 验证：`--ingest --reset` 成功，9 篇文档共 11 个 chunk 入库

### 固定分块「最近标题」取成了块内最后一个标题
- 时间/周次：2026-07-25 / Week 1
- 当时在做：问「年假有多少天」，查看 retrieved chunks 预览
- 现象：命中了正确的《请假与考勤制度》，但预览开头却是「## 6. 迟到与补卡」
- 如何发现：query 时打印的 chunk 预览；对照源文件，文档开头应是制度标题而非第 6 节
- 根因：`chunk_fixed` 在 `start==0` 时对整段 `text[:end]` 取「最后一个标题」当作前缀，短文档一整块时会把文末标题贴到开头
- 处理：改为按字符偏移取 `start` 位置之前的最近标题（`_heading_at`）；若正文已以该标题开头则不再重复前缀
- 验证：重新 ingest 后，同问题 top-1 预览为「# 请假与考勤制度…」，score 从约 0.47 升到约 0.57

### Embedding 单批超过 20 条被网关拒绝
- 时间/周次：2026-07-26 / Week 3
- 当时在做：混合检索改造后，ingest 改为一次 `add` 全部 57 个 chunk
- 现象：embeddings 返回 400，`batch size is invalid, it should not be larger than 20`
- 如何发现：`--ingest --reset` 直接报错
- 根因：当前 MaaS embedding 接口限制单请求 contents ≤ 20；以前按文档分批写入碰巧没踩中
- 处理：`VectorStore.add` 按 `batch_size=20` 分批 embed + upsert
- 验证：`--ingest --reset` 成功，57 chunks + BM25 同步建成

### HuggingFace 拉取 bge-reranker 失败，改用 ModelScope
- 时间/周次：2026-07-27 / Week 3
- 当时在做：接入 cross-encoder 重排，首次加载 `BAAI/bge-reranker-base`
- 现象：HF 下载长时间停在 `.incomplete`；换 `hf-mirror.com` 也报无法连接；缓存损坏后提示缺少 `model.safetensors`
- 如何发现：`--query ... --rerank` 卡住或 Traceback
- 根因：当前网络访问 HuggingFace 不稳定；不完整缓存导致后续加载失败
- 处理：`modelscope.snapshot_download('BAAI/bge-reranker-base')`；`rerank.py` 优先解析 ModelScope 本地路径
- 验证：本地加载成功；XY003 题重排 top1≈0.999 且答对

### Eval 关键词误伤（检索没错，评分 FAIL）
- 时间/周次：2026-07-26 / Week 2
- 当时在做：首轮 golden set 回归（15 题）
- 现象：`sec-l3l4`（L3/L4 能否发个人网盘）FAIL；答案语义正确，用了「禁止」
- 如何发现：`tests/eval/run.py` 输出 `miss=['不得']`；手测答案可读
- 根因：golden `must_contain` 写死「不得」，未覆盖同义词「禁止/不能」
- 处理：评分改为同义组 `["禁止", "不得", "不能", ...]` + 去空格比对（`scoring.py`）
- 验证：扩题后 30 题三路对照均 30/30；说明 **keyword 评分脆**，FAIL 时要先看是评分还是 RAG

### 首次 ingest 因 OPENAI_API_KEY 为空失败
- 时间/周次：2026-07-25 / Week 1
- 当时在做：第一次 `--ingest`
- 现象：embedding 调用失败
- 如何发现：终端报错；检查 `.env` 有 key 名但值为空
- 根因：复制 `.env.example` 后未填真实密钥
- 处理：在 `.env` 填入 DashScope `OPENAI_API_KEY`
- 验证：`--ingest --reset` 成功

### Gradio `gr.State` 在 Blocks 外创建导致 KeyError: 0
- 时间/周次：2026-07-30 / Week 5
- 当时在做：Gradio 界面发第一条消息
- 现象：服务已启动（`http://127.0.0.1:7860`），点击发送后终端 `KeyError: 0`，对话无响应
- 如何发现：终端 traceback 指向 `gradio/state_holder.py`；`state[block._id]` 找不到 id `0`
- 根因：`turn_state = gr.State([])` 写在 `with gr.Blocks()` **之外**，Gradio 6 未注册该 State
- 处理：将 `gr.State(value=[])` 移入 `Blocks` 内；状态存 `list[dict]` 再转 `ChatTurn`
- 验证：重启 `uv run python -m rag_assistant.ui`，多轮问答与右侧检索详情正常

### 项目迁移后 `.venv` 的 activate 仍指向旧路径
- 时间/周次：2026-07-30 / Week 6
- 当时在做：`uv sync --extra ui` 与 `source .venv/bin/activate`
- 现象：`uv` 警告 `VIRTUAL_ENV=.../500-AI-Agents-Projects/...` 与当前项目 `.venv` 不匹配；`pytest` 等 dev 包被卸
- 如何发现：`uv sync` warning；`activate` 内 `VIRTUAL_ENV='...旧路径...'`
- 根因：整个项目（含 `.venv`）从旧目录拷贝过来，`bin/activate` 写死创建时的绝对路径
- 处理：`rm -rf .venv && uv venv && uv sync --extra dev --extra ui`；日常优先 `uv run` 少依赖 activate
- 验证：`echo $VIRTUAL_ENV` 指向当前项目；`uv sync --extra dev --extra ui` 无 warning

### 多跳关系题被 rerank 低分过滤滤空，最后走到拒答
- 时间/周次：2026-08-16 / Week 11
- 当时在做：写 `run_graph_compare.py`，想量化图检索相对文档检索的收益
- 现象：「周凯的隔级上级是谁？」「订单服务间接依赖哪些服务？」走文档 hybrid 检索命中 **0** 条，链路直接走到拒答；「报销审批链有哪些环节？」只命中 1 条弱相关
- 如何发现：对照脚本输出；回查语料确认「周凯的上级是何北」「何北的上级是苏晚」两条事实**都在库里**，不是语料缺失
- 根因：答案要跨两条边拼接才成立，没有任何**单个** chunk 在字面或语义上接近「隔级上级」；召回来的碎片经 cross-encoder 打分后低于 `REFUSE_MIN_RERANK_SCORE`，被 `filter_chunks` 全滤掉
- 处理：认定这类题不该靠调大 k 或关 rerank 硬救——那只会放低分噪音进来。改由 Neo4j + `query_relations` 承接多跳；golden 里给这三题标 `skip_direct_eval`，避免直连 eval 报一个本来就够不到图库的假失败
- 验证：图检索三题 3/3 命中；routing 9/9，三道关系题都选中 `query_relations`

### 首版 Graph RAG 绑死了练习语料，是 demo 不是生产
- 时间/周次：2026-08-16 / Week 11
- 当时在做：第一版 `ingest-graph` + `query_relations`，三道演示题已经能答对
- 现象：能跑通，但换个写法就废——抽取直接按「直属上级」这个具体表头取值，意图判断是一串关键词 if-else，审批链的流程名写死成「费用报销」
- 如何发现：被追问「这是实际生产的处理方法，还是针对编造语料做的处理」，逐条对照后确认是后者：规则写在了这三张表的**数据形态**上，没有抽象层
- 根因：把「让演示题通过」当成了完成标准。演示题通过和方法可迁移是两件事，前者不蕴含后者
- 处理：补 `graph/schema.py` 定义本体——允许的关系类型、列角色同义词（「直属上级 / 上级 / 汇报对象 / manager」都映射到同一角色）；`graph/identity.py` 以通讯录为人员主数据做工号/姓名对齐；查询改为 LLM 只出受校验的 `GraphPlan`，Cypher 用代码里的参数化模板，规划失败降级本体词典且不写死流程名
- 验证：单测 61 passed；全量重建 Person=10 / Service=5 / Step=4 / 边=16；手测「周凯的隔级上级」日志为 `pattern=reports_to hops=2`，答案仍是苏晚

### ReAct 并行调工具 + 本地 rerank 导致进程崩溃（exit 139）
- 时间/周次：2026-08-02 / Week 9
- 当时在做：复合题 `--react`（报销 + 打印机），Agent 一次发出多个 tool_call
- 现象：两个 `rerank.loading`、MPS 上 `Batches: 0%` 后 segfault；`resource_tracker: leaked semaphore`
- 如何发现：终端 `last_exit_code: 139`；日志显示两次并行 hybrid + rerank
- 根因：LangChain 并行执行多个工具；`CrossEncoder` 在 MPS 上非线程安全；曾用普通 `Lock` 嵌套 `_get_model` 还会死锁
- 处理：`retrieval/rerank.py` 用 `RLock` 串行化加载与 `predict`；工具统一为只检索（`run_kb_retrieve`）
- 验证：复合题 `--react` 可跑完并出现 `agent.react_done`（约 1 分钟级）
