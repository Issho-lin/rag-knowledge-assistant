# 面试复习：模拟对话与口述稿

> **用途**：面试前练「讲清楚项目」，而不是背代码名词。  
> **写法原则**：先讲业务问题和设计理由，再必要时点一句实现；技术字段名见文末「备查」。  
> **维护**：新功能或 eval 基线变化后，更新「能力快照」「模拟对话」和 changelog。

---

## 能力快照（面试前核对数字）

| 项 | 当前值（截至 2026-08-20） |
|----|---------------------------|
| 场景 | 虚构「星云科技」内部制度 / FAQ / 通讯录 / PDF 手册 / 组织与依赖关系问答 |
| 语料规模 | 文档侧 **14** 篇（MD/HTML/CSV/PDF）→ **72** 块（policies=63 / tabular=1 / pdf=8）；关系侧 **3** 篇 MD + 通讯录 |
| 图谱规模 | Person **10** / Service **5** / Step **4**，边 **16**（REPORTS_TO / DEPENDS_ON / NEXT） |
| 知识库 | 四库 policies / tabular / pdf / **relations**；前三库**物理分库**（各自向量 collection + BM25 索引）+ Profile，第四库走 Neo4j |
| 存储 | 向量 `qdrant\|chroma`；关键词 `opensearch\|pkl`；图 **Neo4j**；CI 默认 Chroma + pkl，不连图 |
| 入库 | `--ingest` **增量**（`doc_id` + `file_hash`）；`--ingest-graph` **增量**（`SourceDoc.file_hash`）；`--reset` 全量 |
| 回归题集 | **37** 道人工题（含 **3** 道「库外应拒答」、**3** 道关系题） |
| 答案通过率 | **33/34**（`run.py`，Qdrant+OpenSearch；3 道关系题标 `skip_direct_eval` 不计；1 题 `release-window` 漏写「双人复核」，检索已命中） |
| 检索召回 | **31/31**（前 4 条是否命中期望文档；拒答题与关系题不计） |
| 路由选型 | **9/9**（`run_routing.py`：`--agent` 工具选型，含 3 道关系题选中 `query_relations`） |
| 图 vs 文档对照 | 3 道关系题：文档检索命中 0 / 0 / 1，图检索 **3/3** 命中（`run_graph_compare.py`） |
| ReAct 端到端 | **6/7**（`run_react.py`，7 题子集） |
| 单测 | **61** passed（默认 Chroma + pkl，含增量入库与图抽取；图单测不连 Neo4j） |
| 检索方案对照 | 纯向量 / 混合 / 混合+重排，在本题集上分数相同 |
| **默认演示 / 产品路径** | **`--react` ReAct**（CLI 与 Gradio 一致） |
| 辅助路径 | `--query` 全库直连 RAG（eval 底座）；`--agent` 路由单库（理解对照） |
| 多轮 | 有对话历史时才用便宜模型改写问句；单轮不改写 |

---

## 已实现 vs 未实现

**已做完的**：入库（含 PDF）、**物理分库 + Profile**、**可切换存储**（Qdrant/Chroma、OpenSearch/pkl）、**增量入库**、混合检索、重排、带来源的回答、规则+模型两层拒答、多轮改写、**Agent 工具路由（`--agent`）**、**ReAct 多工具（`--react`，CLI 与 Gradio 主路径）**、**Graph RAG（Neo4j + `query_relations`，规则 ETL + 实体对齐 + 参数化 Cypher）**、可观测、可重复评测。

**还没做的**（被问到如实说）：多模态检索、CRAG / Self-RAG 纠错、扩大 ReAct golden、Ragas 自动化打分、异步入库队列、图谱的时效性（关系没有生效/失效时间）。

---

## 口述稿

### 30 秒

我做了一个公司内部知识助手：员工问年假、报销、工号、设备手册这类问题，系统从**多套知识库**里检索相关段落，由 **ReAct Agent** 选库、可多步查资料，再综合片段写答案并标明出处。问「谁的上级是谁」「这个服务依赖什么」这种关系题时，它会转去查一个**知识图谱**而不是硬搜文档。问库外内容或检索很不相关时会拒答。我建了 37 道题做回归测试，检索目前全过，答案偶尔会漏一个要点，也有命令行可以演示。

### 1 分钟

这个项目模拟的是**企业内部知识助手**。员工用口语提问，系统从制度、FAQ、通讯录、PDF 手册等文档里找依据再回答，并且能说明**答案引自哪份文件**。

离线阶段，我把 Markdown、网页、表格、PDF 读进来，按**知识库 Profile** 分块——制度按章节、表格按行、PDF 固定窗口——然后写入**三个物理库**（每套 KB 自己的向量索引和 BM25）。另有一条并行的入库链路，把组织架构、系统依赖、审批流这类文档抽成**三元组写进图数据库**。两条链路都是增量：文件没改就跳过，改了整篇换掉，删了的从索引清掉。用户不用自己选库。

在线阶段，默认走 **ReAct**：Agent 根据问题决定调用哪个工具，必要时**连续查多个库**（比如制度 + 表格），每次工具只返回检索片段，由 Agent 读 Observation 后写最终答案。文档类工具内部是 hybrid 召回 + rerank + 低分过滤；关系类工具则把问题变成一个**查询计划**再去图里跑 Cypher。如果检索明显不靠谱，工具层会提示「未检索到」，Agent 可换库或拒答。

质量上，我用手写题集做回归，分别看「答得像不像」和「该找的文档有没有找进来」；另有一套 routing 小题验证 Agent 会不会选错库，以及一组关系题的图 vs 文档命中对照。

### 3 分钟

在 1 分钟版上，补充**为什么这么设计**：

**多库而不是单库**：企业语料类型差很多——制度是长文、通讯录是表格行、后勤是 PDF 手册。混在一起用同一套切块和检索参数，表格专名和 PDF 都容易吃亏。所以 Registry 里几套库，各自 Profile。早期是一个大索引加 `kb` 标签过滤；第 10 周改成**物理分库**，每个 KB 独立 collection / index，工具一选库就直连对应存储，召回阶段不用再扫全库再 filter。对外还是 Agent 选工具，用户无感。

**为什么还要一个图库**：有一类问题向量检索天然做不了——「周凯的隔级上级是谁」。语料里只写了「周凯的上级是何北」「何北的上级是苏晚」，两句话分在不同段落，没有任何一段的字面或语义接近「隔级上级」，rerank 还会因为分数低把它们全滤掉。这不是召回调参能救的，是**信息本身要靠多跳拼接**。所以我把这类关系抽成图，多跳交给 Cypher 的变长路径去走。它是第四个工具，不是替代向量检索——制度条文仍然走文档 RAG。

**增量入库**：以前改一个文件就要全量 embedding。现在文件没改就跳过；改了按整篇把旧块删掉再写（切块一变，旧 chunk id 对不上，按篇换更干净）；磁盘上删了的索引也清掉。向量和 BM25 一起做。`--reset` 还能全量重建。

**ReAct 而不是只做路由 + 单库 RAG**：复合题「报销额度 + 打印机卡纸」往往跨库。`--agent` 路由只能选**一个**库，复合题容易只查一半就拒答；ReAct 允许 Agent **多轮调工具**，每轮换 query、换库，更接近真实办事流程。工具层统一约定**只返回片段、不调生成 LLM**，避免和 Agent 抢答。

**混合检索 + 重排**（工具内部共用）：向量擅长语义，BM25 擅长工号专名；RRF 按排名融合。粗召回多拉候选，cross-encoder 精排后 `filter_chunks` 滤低分。本题集上三路分数相同，但专名类手测混合更稳，默认仍开重排。

**拒答**：工具层 `pre_llm_refusal` 处理无 chunk / 低置信度；ReAct 终答若仍写「无法确认」再标模型拒答。`--query` 路径还会在检索后、生成前直接拒答省一次 LLM。

**评测分层**：答案 golden（34 题）、检索 recall@4（31 题）、路由（9 题）、ReAct 端到端（7 题，**6/7**）、图 vs 文档对照（3 题）分开看。

**局限**：题集仍小；ReAct eval 有 1 题已知 flake（复合 FAQ）；未上 Ragas 与多模态；图谱只有三类关系、没有时效字段（人事调动后旧边不会自动失效）；增量入库不是跨存储事务，写到一半挂了几边可能暂时对不齐。

---

## 模拟面试对话

> 下面用 **Q / A** 格式。回答按**口头表达**来写：像跟面试官聊天，不要念提纲。  
> 心里可以有结构（先点题、再展开、最后收一句），但嘴上尽量用完整句子串起来，少贴「结论：」「第一步：」这种标签。

---

### 场景 A：项目开场

**Q：** 介绍一下你这个 RAG 项目。

**A：**

我做的是一个企业内部知识助手，场景是虚构的「星云科技」。员工可以问请假、报销、IT 权限、发布窗口、通讯录查人、办公设备 PDF 这类问题。系统从**多套已入库知识**里检索相关段落，默认用 **ReAct Agent** 决定查哪个库、可否多步查，再综合片段组织答案，并把引用的文件标出来。

对我来说，这个项目不只是「能调通 API」，而是想把从入库、分库、检索、Agent 编排到评测、演示整条链路都走通：文档更新了能重新入库；改了检索或 Agent 提示词，能用固定题集看有没有变差；出了问题能分清是检索、路由还是生成；库外问题也要能稳定拒答。

**Q：** 为什么用 RAG，不微调一个大模型？

**A：**

主要是三个考虑。第一，制度文档会更新，RAG 重新入库就行，不用每次改文档都重训模型。第二，企业场景很在意溯源，用户和审计都要知道依据来自哪条制度，RAG 天然能把检索到的段落和生成的句子对应起来。第三，我们这个语料规模和阶段，用 RAG 迭代更快——分块、检索、提示词、Agent 工具可以分开试，微调的试错成本更高。

不是说微调不好，只是当前更需要「文档外挂、可解释、可换库」这条路。

---

### 场景 B：检索与分块

**Q：** 文档是怎么切块的？为什么这样切？

**A：**

语料分三类：中文制度 Markdown 按**标题**切；CSV 通讯录按**行**切，方便工号精确匹配；PDF 手册没有稳定标题，按**固定窗口**切（大约 800 字一块）。每类对应一个知识库 Profile，入库后进各自的物理索引。

这样切是因为不同类型文档的「自然单位」不一样。制度按条款写，按标题切能保证每一块是一个完整主题；表格按行切，检索命中就是一整行记录；PDF 若按固定字符切，容易把操作步骤拦腰截断。

早期单库时用固定长度切还踩过坑：补标题逻辑写错会把最后一节标题误贴到块开头。后来改成 Profile 分块 + 多库，这类问题少很多。

**Q：** 为什么不用纯向量检索？

**A：**

纯向量对「年假有多少天」「差旅标准」这类语义相近的问题已经不错，但企业文档里还有很多字面特征很强的查询，比如工号、文件名、制度编号。这类问题关键词检索往往更稳。

所以我做了两路召回：一路看语义，一路看词匹配，再把结果合并。合并时没有直接按分数加权，因为向量分和 BM25 分的数值范围差很多。我改用按名次融合——两路各自排第几，再合成总排名。

在本项目 34 道回归题上，纯向量和混合检索分数一样，说明这套题对向量已经友好；但我仍默认开混合，因为手测里工号、专名类问题混合更放心。而且现在检索发生在**各 KB 工具内部**，表格库尤其依赖字面匹配。

**Q：** 重排是干什么的？值得加吗？

**A：**

粗召回阶段我会故意多拿一些候选，比如十几条，目的是别漏。但拿多了以后，里面难免有沾边但不相关的段落，直接取前几条给大模型，会浪费上下文，也可能带偏答案。

重排就是在这些候选里再做一次精筛：用交叉编码器对「问题和段落」配对打分，最后只留最相关的几条。召回负责广度，重排负责精度。

ReAct 还有一个工程细节：Agent 可能**并行调多个工具**，多个线程同时跑重排会在 Mac MPS 上崩，所以我对 rerank 加载和推理做了串行锁。这是典型的「算法对了、部署形态还要适配」。

**Q：** 你们怎么衡量检索好不好？

**A：**

我不会只看最终答案对不对——答案写对了，检索有可能是碰运气。所以要单独看检索有没有找对文件：每道测试题人工标好「理想情况下应命中哪份制度」，再看系统返回的前 4 条里有没有这份文件。

34 道题里有 3 道是故意设计的库外题，本来就不该命中任何内部文档，不计入这项统计；剩下 31 道目前都是找对了。

这套 eval 走的是「检索 + `produce_answer`」直连路径，和线上一致的检索链，但**不是** ReAct 端到端。ReAct 我另外用手测复合题和 routing 6 题验证选库。

**Q：** 这套评测体系具体是怎么设计的？

**A：**

RAG 是先找材料再写答案，评测我也刻意拆成多层。考卷 34 道题，覆盖正常制度题、复合题、工号专名、跨库 routing，还有 3 道库外拒答题。每道题人工写好问法、要点、期望文档、部分题还标期望工具名。

跑起来之后：答案层看要点和拒答；检索层看 recall@4；routing 层另 6 题只看 `--agent` 会不会选错 `search_*`。库外题不评检索，只评有没有老实说不确定。

目前生产配置（Qdrant + OpenSearch + Neo4j）下答案 33/34，检索 31/31，路由 9/9。掉的那题是生成漏写「双人复核」，检索已经找对文档。局限我也主动说：题集不大；主 eval 不是 ReAct 全链路；要点判分对措辞敏感，更多是抓回归趋势。

**Q：** 跑完以后报告里记什么？挂了怎么查？

**A：**

报告分块汇总：通过率、recall、检索模式（vector / hybrid / rerank）。逐题明细记实际问句、答案、要点命中、检索文件、是否拒答。

某题 FAIL 打开报告分诊：检索没找对看候选和分数；生成写漏看 must_contain；库外题没拒答看是否该走规则拒答；routing 挂看是不是 composite 题却只选了单库工具。

---

### 场景 C：生成、拒答、引用

**Q：** 怎么防止模型胡编？

**A：**

我分了不止一道防线。

在 **`--query` / `--agent`** 路径：重排后分数过低会直接拒答，不再调生成模型；生成提示词也要求无依据就说「无法确认」。

在 **`--react` 路径**：每次工具检索后走同样的 `pre_llm_refusal` 和 `filter_chunks`；Observation 会写「未检索到相关片段」或低置信提示，Agent 可以换库。最终若 Agent 仍输出拒答话术，结果里标为模型拒答。工具层**不会**替 Agent 写完整答案，避免和 ReAct 逻辑打架。

测试集里 3 道库外题要求必须拒答，产品和测试对「什么叫拒答成功」用同一套 `is_refusal` 判断。

**Q：** 拒答为什么分「规则拒答」和「模型拒答」？

**A：**

规则拒答处理的是明显不该问模型的情况：没检索到东西，或未开 rerank 时相关性分数已经低到可以判定「文档里没有」。直连 RAG 这时直接返回，不调大模型。

模型拒答处理灰色地带：检索回来的段落看起来有点相关，但细读并没有答案——直连 RAG 靠 `produce_answer` 提示词；ReAct 靠 Agent 读 Observation 后自己判断。

可以概括成：能靠检索分数判断的，就别浪费一次生成；判断不了的，再交给模型读段落决定。

**Q：** 答案里的「来源」是怎么做的？

**A：**

我让模型在正文里用编号标注依据，比如「满 1 年 5 天 [1]」。程序解析 `[1][2]`，用 `build_citations` 拼「参考来源」区块：文件名、分数、预览，并区分「正文引用了」还是「检索命中但未写入答案」。

ReAct 会把**多次工具调用**的 chunks 合并后再建引用，所以复合题也能列出各库命中的片段。

---

### 场景 D：多轮与产品

**Q：** 多轮对话怎么支持？

**A：**

用户经常会连续追问，比如先问「年假有多少天」，再问「那病假呢」。第二句单独拿去检索，系统很难理解「那」指什么。

有历史时先用便宜模型把当前问题改写成可独立检索的完整问句，再进入 ReAct 或直连 RAG。界面上可以展示「检索问句」方便调试。

只有存在对话历史时才改写；第一轮不额外调模型，避免把短问句改偏。

**Q：** 命令行和网页是不是两套逻辑？

**A：**

已经是一套。CLI `--react` / `--chat --react` 和 Gradio 都走 `query_agent_react`，检索和工具层共用。`--query` 留给评测和对照实验。

---

### 场景 E：评测与工程

**Q：** 改完一版怎么知道是变好还是变差？

**A：**

用固定考卷，**一次只动一个变量**。改检索就只切 retrieve/rerank；改 Agent 就手测复合题 + 跑 routing；改语料就 `--ingest` 增量，切块或存储结构变了再用 `--reset` 全量。对照结果存成报告文件。

**Q：** 测试失败了你怎么查？

**A：**

先对着报告分诊：检索、生成、拒答、routing 四类。ReAct 手测时看 `agent.react_done` 日志里调了哪些工具、几次。多轮追问答偏先看改写后的问句。

排查过程记在 `rag-pitfalls.md`，比如 ReAct 并行 rerank 导致 MPS 崩溃、RLock 死锁等。

**Q：** 为什么没上 Ragas 这类框架？

**A：**

分阶段。早期先把手写要点 + recall + routing 习惯建立起来，便宜、透明、好解释。Ragas 适合后面加「是否忠于检索」一层。ReAct 端到端自动评测也同理，还没上，不是不想做。

**Q：** 线上出问题怎么观测？

**A：**

接了可选 Langfuse。`--react` 有 `rag-react-query` → `agent-react` 两层 span；直连 RAG 还有 `generate`。主要盯改写、检索、生成（或 Agent 终答）三段，够定位大部分问题。

---

### 场景 F：Agent、ReAct 与多库（第 9 周重点）

**Q：** 为什么要有多个知识库？用户不是要「一个助手」吗？

**A：**

对用户是一个助手，对系统是多套语料类型。制度、表格、PDF 的最优切块和检索增强不一样——比如 policies 开父文档扩展，tabular 按行、更吃 BM25。

早期是一个大索引加 `kb` 标签过滤，demo 好做。第 10 周改成物理分库：每个 KB 自己的 Qdrant collection（或 Chroma 目录）和 OpenSearch index（或 pkl）。Agent 选中 `search_policies`，检索就只打 policies 那一套库，不用先搜全库再 filter。隔离更好，也方便以后按库扩容。CI 仍可用 Chroma + pkl，生产切环境变量就行。

**Q：** `--agent` 和 `--react` 有什么区别？为什么主路径选 ReAct？

**A：**

两者都用同一套 `search_*` 工具，工具**只返回检索片段**。

`--agent` 是 cheap LLM **function calling 路由**：一次选一个库，然后 Python 调 `produce_answer` 写答案。简单题够用，复合题容易「只查一个库就结束」。

`--react` 是 strong LLM **ReAct 循环**：可以自己决定调几个工具、每个工具传什么子问句，读完 Observation 再写终答。复合题、跨库题明显更稳。

所以我把它定为**演示和生产主路径**；`--query` 留给 eval 和对照实验；`--agent` 留给理解「路由」和 routing 评测，不叠第三层「agent vs react 再路由」。

**Q：** 工具为什么只返回片段，不在工具里直接生成答案？

**A：**

职责分离。检索链（hybrid、rerank、过滤）已经比较复杂，生成又有自己的提示词和拒答逻辑。若工具内嵌 `produce_answer`，ReAct Agent 读到的就不是「原始材料」，无法跨工具综合，也没法在「A 库没查到」时自主换 B 库。

统一约定后：`run_kb_retrieve` 是所有路径的检索入口；`build_kb_tools` 只格式化 Observation；`--query`/`--agent` 在 Python 层调 `produce_answer`；`--react` 由 Agent 写答案。

**Q：** ReAct 的完整链路你怎么讲？

**A：**

用户问题进 `query_agent_react` → 可选多轮改写 → `run_react_agent` 建 LangChain Agent 图 → Agent 发 tool_call → 工具内 `run_kb_retrieve` → `retrieve_chunks` → hybrid + rerank + filter → 片段格式化成 Observation 回 Agent → 循环直到 Agent 输出无 tool_calls 的最终 AIMessage → 合并各次 chunks、`build_citations`、封装 `QueryResult` → CLI 打印。

**Q：** 复合题举个例子？

**A：**

比如「报销住宿标准是多少？打印机卡纸怎么办？」。ReAct 可能先 `search_policies` 查差旅标准，再 `search_pdf_handbook` 查设备手册，两次 Observation 都看完后写一条综合答案。`--agent` 路由往往只能选一个库，另一类信息就丢了。

---

### 场景 G：存储与增量入库（第 10 周）

**Q：** 向量库和关键词索引现在怎么存？

**A：**

两套都能切。向量默认可以走本地 Chroma，生产切 `VECTOR_BACKEND=qdrant`；关键词默认 `bm25.pkl`，生产切 `BM25_BACKEND=opensearch`。检索接口一样，hybrid + RRF 行为不变。Docker 里 Qdrant、OpenSearch、Neo4j 一起起，图库在第 11 周接上了 `query_relations`。

每个知识库是独立索引，不是一个大库打标签。CI 没有 Docker，单测仍用 Chroma + pkl，图相关的单测只测抽取和查询规划，不连 Neo4j。

**Q：** 增量入库是怎么做的？为什么不按 chunk 更新？

**A：**

磁盘当准，索引跟着变。每篇文件两个值：路径算出 `doc_id`（这是哪篇），文件字节算出 `file_hash`（有没有改）。对照索引里已有的指纹：没改的跳过，连 embedding 都不跑；新文件或内容变了的写入；索引有、磁盘没了的删掉。

内容变了要先按 `doc_id` 把这篇旧块全删再写。因为切块数量、每段正文都会变，chunk id 还带了正文哈希，你手里只有新 id，不知道旧的哪些该删。按文档整篇换最干净。新文件也走同一条「先删再写」，库里没有就是空删。

按 chunk 做差集也行，得先把这篇在索引里的旧 chunk id 查出来再加减。大文件只改一小节时能少 embed，但固定窗口一切错位，几乎整篇都变，划不来。我们语料不大，按文档够用。

向量库和 BM25 必须一起删一起写，不然两边对不齐。第一次从旧全量索引升级，没有 `doc_id` 的遗留块会先清掉再按新格式写入。

**Q：** 文件改名了怎么办？写到一半挂了呢？

**A：**

路径变了 `doc_id` 就变了，旧路径当删除，新路径当新文件。这是用路径当身份的代价，以后要稳定可以换成业务文档 ID。

现在不是跨存储事务，向量写完 BM25 挂了会对不齐，这是缺口。生产要补重试或对账。`--only` 只同步一个语料包时，删除范围也只限这个包，避免把没加载的包当成磁盘删除。

---

### 场景 H：关系检索与 Graph RAG（第 11 周重点）

**Q：** 为什么要引入图数据库？向量检索不够吗？

**A：**

不是向量检索调得不够好，是有一类问题它**结构上就答不了**。比如「周凯的隔级上级是谁」。语料里从来没有一句话写过这个，只有「周凯的上级是何北」和「何北的上级是苏晚」，还分在表格的不同行。你把 k 调大、把 rerank 关掉都没用——答案需要把两条边接起来才存在。

我实测过：这三道关系题走文档 hybrid 检索，两道命中 0 条，一道命中 1 条弱相关；rerank 甚至会因为分数低把它们全滤空，最后走到拒答。换成图检索三道全中。所以我加的是**第四个工具**，不是替换向量检索，制度条文那类题仍然走文档 RAG。

**Q：** 图是怎么建出来的？总不能手写 JSON 吧。

**A：**

对，手写 JSON 就变成 demo 了。我的原则是**语料是唯一事实源**，图必须从语料自动抽。

主力是**规则 ETL**。但这里有个关键设计：不能绑死某一篇文档的列名。我在本体里定义了「列角色」和它们的同义词——「直属上级 / 上级 / 汇报对象 / manager / reports_to」都映射到 `manager` 这个角色。抽取时先认表头属于哪个角色，再按角色取值。换一篇列名不同的表，不用改代码。

第二层是**实体对齐**。同一个人在通讯录里是「周凯 + 工号 XY007」，在架构文档里可能只写「周凯」，也可能只写工号。我拿通讯录当**人员主数据**建索引，把姓名和工号都归一到同一个规范名，否则图里会出现两个不连通的「周凯」，多跳直接断掉。

第三层才是 **LLM 补抽**，用来捞散文里规则表达不了的关系。但它被限制得很死：只允许输出本体里定义的关系类型，越界的丢弃。审批环节的**顺序**我明确不让 LLM 抽——它很容易把顺序打乱，而有序列表的序号是确定信息，用规则读更可靠。

入库也是增量的：每篇源文档在图里有个 `SourceDoc` 节点存 `file_hash`，没变就跳过；变了先把这篇 source 产生的边删掉再重新 MERGE，避免改文档后留下幽灵关系。

**Q：** 查询时是让大模型写 Cypher 吗？

**A：**

不是，这点我专门避开了。让 LLM 直接写 Cypher 有两个问题：一是它可能写出语法对但语义错的查询，二是等于把数据库执行权交给了模型输出，注入风险没法兜底。

我的做法是让 LLM 只出一个**查询计划**——一个受 Pydantic 校验的结构体，字段就几个：查什么模式（汇报线 / 依赖 / 审批链）、主体是谁、跳几跳、是否要精确跳数。Cypher 模板是代码里写死的，实体作为 `$name` 参数传进去，跳数只接受校验后的 1 到 3 的整数。这样既拿到了自然语言理解能力，又不用防注入。

LLM 规划失败或超时就降级到**本体词典**：问句里有「上级 / 汇报」就走汇报线，有「隔级 / 上级的上级」就把跳数提到 2。降级路径不依赖模型，也不把流程名写死。

**Q：** 图返回的结果怎么接回 Agent？

**A：**

这是我觉得设计上比较干净的一点：**在工具边界统一**。`query_relations` 也返回和文档检索同构的 chunk——有 text、source、score、kb 字段，只是 text 是把路径拼成的自然语言，比如「周凯 → 何北 → 苏晚，共 2 跳」。

好处是 Agent 侧完全不用知道后端是 Neo4j 还是向量库，Observation 格式化、引用合并、拒答判断这些逻辑全都复用。加图库没有动 ReAct 循环一行代码，只是在 `run_kb_retrieve` 里按 `kb.backend` 分了个流。

**Q：** 怎么保证 Agent 不会拿文档工具去答关系题？

**A：**

靠工具描述里写清楚**边界**，正反都写。`query_relations` 的描述里列了典型问法「谁的上级」「A 依赖什么」，同时 `search_policies` 和 `search_tabular` 的描述里明确写了「汇报线 / 依赖链请用 `query_relations`」。

然后用路由 eval 验证，不靠感觉。我在 golden 里给这三道关系题标了 `expected_tool: query_relations`，跑下来 9 道路由题全中。这三道题还标了 `skip_direct_eval`，因为直连 RAG 那条路径根本够不到图库，让它去跑只会得到一个假的失败。

---

### 场景 I：难点与反思

**Q：** 印象最深的难点是什么？

**A：**（选 1 个讲透）

我比较想讲的是 ReAct **并行调工具**时重排模型在 MPS 上直接 segfault。一开始以为是 LangChain bug，后来发现是 CrossEncoder 非线程安全。加锁又踩了死锁——`rerank` 持锁再调 `_get_model` 二次抢锁。最后改成 `RLock` 串行化加载和推理，复合题才稳定跑完。这说明 Agent 路径不仅要算法对，还要考虑**并发形态**。

也可以讲评测误伤：标准只认「不得」、模型写「禁止」导致 FAIL，后来用同义组解决；或库外题拒答文案不统一导致线上信任差，后来固化 `REFUSAL_MESSAGE` 和 `is_refusal`。

**Q：** 继续往下做你会做什么？

**A：**

短期：扩大 ReAct golden；更难复合题；给图谱补时效字段，人事调动后旧的汇报边应该失效而不是留着。

接下来（第 12 周）：多模态检索（架构图/截图）+ CRAG 纠错检索。

长期工程化：题集扩大、Ragas、入库队列和失败重试——增量现在是同步命令，还不是生产任务系统。按 `production-gap.md` 的触发条件来，不提前过度设计。

---

## 备查：代码与字段（自己复习用，面试少主动报）

| 口语说法 | 代码/文件 roughly 对应 |
|----------|------------------------|
| 回归题集 / 金标准题集 | `data/eval/golden.json`（37 题；其中 3 道图题标 `skip_direct_eval`） |
| 路由题集 | 无独立文件，`run_routing.py` 从 golden 里筛 `expected_tool`（9 题） |
| 关键词是否命中 | golden 里 `must_contain` → hits/miss |
| 期望命中的文档 | `expected_sources` → recall@4 |
| 期望工具 | `expected_tool`（routing / 部分 golden） |
| 检索前规则拒答 | `answer/refusal.pre_llm_refusal` |
| 终答拒答检测 | `answer/refusal.is_refusal` |
| 直连生成 | `answer/generate.produce_answer`（`--query` / `--agent`） |
| 来源列表 | 正文 `[1][2]` + `build_citations` / `sources_text` |
| 多轮改写 | `query/preprocess/rewrite.py`，有历史才 cheap 模型 |
| **ReAct 主路径** | `query/modes/agent_react/` → `loop.run_react_agent` |
| ReAct 端到端 eval | `tests/eval/run_react.py` + `data/eval/react_golden.json`（7 题，6/7） |
| KB 工具 | `kb/search.py`：`build_kb_tools`、`run_kb_retrieve`、`format_chunks_observation` |
| 知识库注册 | `kb/registry.py`（policies / tabular / pdf / relations，带 `backend` 字段） |
| 物理分库工厂 | `retrieval/vector_store.py`、`retrieval/bm25_store.py`（按 `kb_id`） |
| 图本体 / 列角色 | `graph/schema.py`：`ALLOWED_RELS`、`COLUMN_ROLES`、`SCHEMA_CARD` |
| 图抽取 | `graph/extract.py`（规则）、`graph/extract_llm.py`（补抽） |
| 实体对齐 | `graph/identity.py`：`IdentityIndex`（通讯录当主数据） |
| 图增量入库 | `graph/ingest.py`：`SourceDoc.file_hash` → 删该 source 的边再 MERGE |
| 图查询计划 | `graph/plan.py`：`GraphPlan` + `infer_plan_from_lexicon` 降级 |
| 参数化 Cypher | `graph/query.py`：`execute_plan`、`_var_len`（跳数只接受 1–3） |
| 增量指纹 | `ingest/fingerprint.py`：`document_id` / `content_hash` |
| 增量同步 | `ingest/run._sync_kb`：跳过 / upsert / 按 `doc_id` 删除 |
| 路由选型（辅助） | `query/modes/agent_route/select.select_tool_names` |
| 直连 RAG（eval） | `query/modes/direct.py` |
| 检索入口 | `query/retrieve.py` → `retrieval/engine.retrieve_with_options` |
| rerank 串行锁 | `retrieval/rerank.py`（ReAct 并行 tool） |
| 三路对照实验 | `tests/eval/compare.py` |
| 图 vs 文档对照 | `tests/eval/run_graph_compare.py` |

---

## 演示命令（面试前可真跑一遍）

```bash
uv sync --extra dev --extra ui
docker compose up -d                                       # Qdrant + OpenSearch + Neo4j
uv run python -m rag_assistant.pipeline --ingest --reset   # 首次全量
uv run python -m rag_assistant.pipeline --ingest           # 之后增量：未改跳过
uv run python -m rag_assistant.pipeline --ingest-graph     # 关系语料 → Neo4j

# 主路径：ReAct
uv run python -m rag_assistant.pipeline --react --query "年假有多少天？怎么折现？"
uv run python -m rag_assistant.pipeline --react --query "工号 XY003 是谁？分机多少？"
uv run python -m rag_assistant.pipeline --react --query "报销住宿标准？打印机卡纸怎么办？"

# 关系题（走 query_relations）
uv run python -m rag_assistant.pipeline --react --query "周凯的隔级上级是谁？"
uv run python -m rag_assistant.pipeline --react --query "订单服务间接依赖哪些服务？"

# 库外拒答
uv run python -m rag_assistant.pipeline --react --query "公司股票期权怎么行权？"

# 多轮
uv run python -m rag_assistant.pipeline --chat --react

# 对照：直连 RAG（与 eval 同路径）
uv run python -m rag_assistant.pipeline --query "年假有多少天？"

# 评测
uv run pytest tests/ -q --ignore=tests/eval
uv run python tests/eval/run.py
uv run python tests/eval/run_routing.py
uv run python tests/eval/run_react.py
uv run python tests/eval/run_graph_compare.py
```

---

## 维护 changelog

| 日期 | 更新内容 |
|------|----------|
| 2026-07-30 | 初版 |
| 2026-07-30 | 场景 E 改为真实问法；备查与模拟对话分离 |
| 2026-07-30 | 评测追问补充考卷/报告内容与 FAIL 分诊示例 |
| 2026-07-30 | **模拟面试改为口语化 Q/A** |
| 2026-08-02 | **第 9 周收尾**：`run_react.py` 6/7、Gradio ReAct、learning-log 归档 |
| 2026-08-16 | **第 10 周收尾**：Qdrant/OpenSearch 可切换、物理分库、增量 ingest；口述同步（Gradio 已是 ReAct） |
| 2026-08-16 | **第 10 周验收**：Qdrant+OS ingest 72 chunk；golden 33/34、recall 31/31、routing 6/6；eval 空库改按 KB 汇总 |
| 2026-08-20 | **第 11 周 Graph RAG**：新增场景 H（关系检索）；四库口径、routing 9/9、单测 61；「还没做的」移除 Graph RAG |

### 新功能迭代时更新清单

- [ ] 更新「能力快照」
- [ ] 在对应场景补充「怎么做的 / 为什么」叙述
- [ ] 备查表如有新模块则增一行
- [ ] changelog 记一笔
