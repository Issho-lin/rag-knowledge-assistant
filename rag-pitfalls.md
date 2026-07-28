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
