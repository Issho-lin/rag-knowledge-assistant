# Eval 回归评测说明

本目录是 **golden set 回归评测**（集成测试），不是主业务代码。  
对固定题集跑「检索 → 生成 → 打分」，用来在改检索/分块/prompt 后做 before/after 对照。

```
data/eval/golden.json          考卷（题 + 断言，人维护）
tests/eval/run.py              跑一轮评测，写 results
tests/eval/compare.py              多组对照（--suite retrieval | enhanced）
tests/eval/scoring.py          纯打分逻辑（无 LLM）
data/eval/results/*.json       成绩单（程序生成）
```

## RAG 效果怎么评

分两层：**口述版**用业务语言讲清楚；**术语对照**把口语和本仓库里的字段、脚本对应起来，自己查文档时用。

---

### 口述版（对外介绍用这个）

**我们在评什么**

本质上就是给 RAG 做**固定考卷的回归测试**。大约 30 道题，都是真实会问的：年假怎么算、权限怎么申请、差旅标准多少，也有故意设计的坑——复合问题、库外问题、以前答错过的地方。每次改检索、改 prompt、换模型，都用同一套题再跑一遍，看分数有没有掉，不靠「感觉好像变好了」。

**分两段看，不混在一起**

RAG 先做两件事：先从文档里**找材料**，再**组织成回答**。评测也分开看：

1. **找材料找对了没有**——系统返回的几条参考片段里，有没有包含应该引用的那份制度/FAQ？
2. **回答写对了没有**——关键数字、流程、专有名词有没有说到？知识库里没有的内容，有没有老实说不确定，而不是瞎编？

两个都要看。只看出没答对，分不清是「没找到文档」还是「找到了但写漏了」；只看找没找到文档，也看不出「材料在手却漏答要点」的情况。某题挂了，先看是找错文档还是写错答案，再决定改检索还是改生成。

**平时怎么跑：单轮回归 + 三路对照**

评测有两种常用跑法，配合不同场景：

1. **单轮回归**——改 prompt、改分块、换模型之后，用当前默认搜法把 30 题全跑一遍，看总分和逐题明细有没有掉。这是日常改代码后的「冒烟 + 回归」。

2. **三路对照**——专门用来**挑检索方案**的。同一批题、同一时刻、只变搜法，连跑三条链路：
   - 路一：只用向量相似度
   - 路二：向量 + 关键词混合检索
   - 路三：混合检索 + 精排模型再筛一遍

   跑完出一张对照表：三条链路各自的「答对率、要点覆盖率、找文档命中率」并排比。哪条路数字更好，再决定默认用哪种搜法。这样 hybrid、rerank 有没有用，不是凭感觉，是对照表上看得见。

平时改业务逻辑用单轮回归；动检索栈或要证明「加混合检索 / 加重排值不值」时，跑三路对照。

**考卷怎么来的**

不是随便编 30 题，而是：

- 自己手测过、确认该对的典型问法
- 曾经暴露过的漏点（比如发布流程漏了「双人复核」）
- 边界情况：一道题问两件事、同义词说法不同、问库外内容该不该拒答

每道题人工写好「标准答案应包含什么要点」「应该引用哪份文档」「库外题是否该拒答」。

**怎么证明某次改动真的有效**

- **改检索**（混合检索、重排序等）→ 跑**三路对照**，看对照表里哪条路「找文档更准、答对更多」
- **改生成**（prompt、分块、模型）→ 跑**单轮回归**，固定搜法只看总分和 FAIL 题有没有新增

只有数字上确实变好，才采纳为默认方案。掉了分就翻 FAIL 题的明细；需要深挖某一题时，用可观测平台看那次请求实际检索到了哪些片段、拼了什么 prompt。

**这套方法的局限（可以主动说）**

- 30 题覆盖的是我们关心的场景，不能代表所有用户问法
- 答案打分目前是**关键词规则**，便宜、稳定、可重复，但对措辞变化敏感；复杂语义还没上 LLM 当裁判
- 拒答只检查是否说了「无法确认」这类固定表达，产品化以后可以更细
- 批量评测看**趋势和回归**；单题排查靠 trace，两者配合用

**试题和结果是怎么设计的**

*考卷（试题）侧——人出题、人定标准，机器只负责跑和判*

每道题在考卷里就是四件事：用户会怎么问、答对应该提到哪些要点、应该去翻哪份内部文档、以及（少数库外题）是否必须拒答而不是硬编。题从手测和真实踩坑里长出来，不是自动生成；备注字段只给人看，不参与打分。

题型上我们刻意覆盖了多种情况：单点制度题、一道题问两件事的复合题、工号/专名这类靠关键词才稳的题、以及知识库里根本没有的库外题（用来测会不会瞎编）。要点断言支持「同义说法算对」——比如答「禁止」或「不得」都算命中，避免模型措辞不同就被误判。

库内题会标注「应该引用哪份文档」，用来单独评检索；库外拒答题只评有没有老实说不确定，不要求找对文档。

*成绩单（结果）侧——程序自动生成，留档可对比*

跑一遍评测，程序对每道题记下：实际问了什么、系统生成了什么回答、哪些要点命中/漏了、检索到的文档列表、以及这道题在「找文档」和「写答案」两关各自过没过。卷首再汇总整轮的通过率、要点覆盖率、检索命中率，并记录这次用的搜法配置和时间——方便和下次跑的结果 apples-to-apples 对比。

**三路对照**还会多生成一份汇总表：同一批题下，三条链路（纯向量 / 混合 / 混合+重排）的分数并排列出，并各指向一份完整明细。文件名带配置名和时间戳，改一次代码留一份快照，掉了分就翻 FAIL 那几题的明细查原因。

打分规则本身是固定的纯逻辑（不另调 LLM 当裁判），所以同样输入每次判分一致；真正会变的是 RAG 检索和生成的输出。

**30 秒版**

> 我们维护了大约 30 道固定业务题，每题人工写好「该答哪些要点、该引用哪份文档、库外是否该拒答」。每次改 RAG 都用同一套题跑完整流程，分开看「有没有找对文档」和「回答要点全不全」。日常改代码跑单轮回归看分数掉没掉；动检索时跑**三路对照**——纯向量、混合检索、混合+重排三条链路同一批题并排比，用对照表证明哪种搜法更好。试题人定标准、结果机器留档，不靠感觉。

---

### 术语对照（查文档、看 JSON 时用）

口述里的说法和本仓库实现的对应关系：

| 口述说法 | 在本项目里 |
|----------|------------|
| 固定考卷 / 约 30 道题 | `data/eval/golden.json` |
| 答案应包含的要点 | `must_contain`（同义说法可写一组，命中其一即可） |
| 应该引用的文档 | `expected_sources` |
| 库外题是否该拒答 | `expect_refuse` |
| 找对文档了吗 | 单题 `recall_hit`；整轮 `recall_at_k` |
| 回答要点全不全 | `keyword_score` / `keyword_miss` |
| 整题是否通过 | `passed`（要点满分 + 拒答检查通过） |
| 整轮答对比例 | `pass_rate` |
| 三路对照 | `compare.py`：vector / hybrid / hybrid+rerank 同一批题并排跑 |
| 三路对照汇总表 | `data/eval/results/compare_latest.json` |
| 单轮评测 | `tests/eval/run.py` |
| 成绩单（单路） | `data/eval/results/<tag>_<时间戳>.json` |
| 卷首汇总（通过率、检索命中率、配置） | results 文件头：`pass_rate`、`recall_at_k`、`retrieve`、`tag` 等 |
| 单题明细（实际回答、命中/漏点、检索到的文档） | results 的 `items[]` |
| 同义说法算对 | `must_contain` 里的字符串数组 |
| 给人看的出题备注 | `notes`（不参与打分） |

**口述 vs 字段名**：对外讲用左边一列；只有对方追问实现细节，或你自己查 FAIL 原因时，再用右边这些名字。

---

## 怎么跑

在项目根目录执行：

```bash
# 全量或调试（--limit 只跑前 N 题）
uv run python tests/eval/run.py
uv run python tests/eval/run.py --limit 3

# 指定检索配置
uv run python tests/eval/run.py --retrieve vector --no-rerank --tag vector_norerank
uv run python tests/eval/run.py --rerank --tag hybrid_rerank

# 三路对照
uv run python tests/eval/compare.py --limit 3

# 只测打分规则（不调 LLM，毫秒级）
pytest tests/eval/test_scoring.py -q
```

---

## `data/eval/golden.json` 字段说明

文件是一个 **JSON 数组**，每个元素是一道测试题。

| 字段 | 类型 | 必填 | 程序是否读取 | 含义 |
|------|------|------|--------------|------|
| `id` | string | 是 | 是 | 题目唯一标识，便于在 results 里对照 |
| `question` | string | 是 | 是 | 送给 RAG 的用户问题 |
| `must_contain` | array | 是 | 是 | **答案侧**断言：最终回答里必须覆盖的要点 |
| `expected_sources` | array | 库内题建议有 | 是 | **检索侧**断言：top-k 结果里应命中的语料文件名（子串匹配） |
| `expect_refuse` | boolean | 是 | 是 | 是否要求拒答（库外题设为 `true`） |
| `notes` | string | 否 | **否** | 给人看的备注，不参与打分 |

### `must_contain` 写法

数组里每一项是一条断言，**全部满足**才算 keyword 满分：

| 写法 | 含义 | 示例 |
|------|------|------|
| 字符串 | 答案里必须包含该子串（比对前会去掉空格，`5 天` ≈ `5天`） | `"ITSM"` |
| 字符串数组 | **同义组**：命中其中任意一个即可 | `["禁止", "不得", "不能"]` |

### `expected_sources` 写法

- 写语料**文件名或其中一段**，与 chunk 的 `source` 路径做子串匹配。
- 例：`"02-请假与考勤制度.md"` 表示 top-k 里至少有一个 chunk 来自该文件。
- **拒答题**（`expect_refuse: true`）通常不写此字段；不写则不计入 recall 统计。

### `expect_refuse`

| 值 | 含义 |
|----|------|
| `false` | 正常答题；`refuse_ok` 恒为 true，不检查拒答 |
| `true` | 库外题；答案里须含「无法确认」（去空格后匹配），且 `must_contain` 里一般也有 `"无法确认"` |

---

## `data/eval/results/*.json` 字段说明

以 `hybrid_rerank-default_20260728_232605.json` 为例：一次 `run()` 的完整输出。  
结构分为 **文件头 summary** 和 **每题明细 items**。

### 文件头（整次 run 的汇总）

| 字段 | 示例值 | 含义 |
|------|--------|------|
| `created_at` | `"2026-07-28T15:26:05.617493+00:00"` | 本次评测完成时间（UTC） |
| `retrieve` | `"hybrid"` | 使用的检索模式：`hybrid` 或 `vector` |
| `use_rerank` | `null` / `true` / `false` | 是否启用重排；`null` 表示未指定，用了 `.env` 默认 |
| `k` | `4` | 检索返回的 chunk 条数（top-k） |
| `tag` | `"hybrid_rerank-default"` | 本次 run 的标签，用于结果文件名前缀 |
| `n` | `3` | 实际跑的题目数（全量约 30；示例为 `--limit 3`） |
| `pass` | `3` | `passed: true` 的题数 |
| `pass_rate` | `1.0` | 通过率 = `pass / n` |
| `avg_keyword_score` | `1.0` | 各题 `keyword_score` 的算术平均 |
| `recall_at_k` | `1.0` | 检索 recall 命中率（见下） |
| `recall_n` | `3` | 参与 recall 统计的题数（有 `expected_sources` 的题） |
| `recall_hit` | `3` | `recall_hit: true` 的题数 |
| `items` | `[...]` | 每道题的明细数组 |

**`recall_at_k` 计算**：`recall_hit / recall_n`。只统计 golden 里写了 `expected_sources` 的题；拒答题不计入。

### `items[]` 每题明细

| 字段 | 含义 |
|------|------|
| `id` | 对应 golden 里的题目 id |
| `question` | 本题问题（从 golden 复制） |
| `answer` | 本次 RAG **实际生成的完整回答** |
| `keyword_hits` | `must_contain` 里**命中**的词（同义组命中时记录实际匹配到的那个） |
| `keyword_miss` | `must_contain` 里**未命中**的断言（同义组未命中时显示 `(禁止\|不得\|...)`） |
| `keyword_score` | 关键词命中率 = `len(keyword_hits) / len(must_contain)`，范围 0～1 |
| `refuse_ok` | 拒答检查是否通过（见 golden `expect_refuse`） |
| `passed` | **本题是否通过**：`keyword_score >= 1.0` 且 `refuse_ok` |
| `expected_sources` | 从 golden 复制的「应命中语料」 |
| `retrieved_sources` | 本次 top-k 检索到的 chunk 的**文件名**列表（去重、保序） |
| `recall_hit` | 检索是否合格：`expected_sources` 每一项都在 top-k 的 source 路径中出现 |
| `recall_miss` | 未在 top-k 中命中的 expected 文件名 |

### 如何读一题的结果

| `passed` | `recall_hit` | 通常说明 |
|----------|--------------|----------|
| false | false | 检索可能有问题，生成也可能有问题 → 先看检索 |
| false | true | 材料找到了，但答案缺要点或拒答不对 → 偏生成/prompt |
| true | false | 答案碰巧对了，但检索没召回到预期文档 → 检索仍值得修 |
| true | true | 本题通过 |

---

## 跑出来的结果应该怎么看

Eval 有两层输出：**终端实时打印**（跑的时候看）和 **JSON 文件**（跑完留档、做对照）。

### 第一步：看终端 —— 跑的过程中

每道题会打印一行结论，格式如下：

```
[1/3] leave-annual: 年假有多少天？怎么折现？
  -> PASS  keyword=1.0  miss=[]  recall=R✓
```

| 片段 | 含义 |
|------|------|
| `[1/3]` | 第几题 / 共几题 |
| `leave-annual` | golden 里的题目 id |
| `PASS` / `FAIL` | 本题是否通过（= `passed`） |
| `keyword=1.0` | 答案关键词得分（1.0 = 满分） |
| `miss=[...]` | 没命中的 `must_contain`；空数组 = 全命中 |
| `recall=R✓` / `R✗` | 检索是否召回到 `expected_sources` |

跑完末尾还有汇总：

```
======== eval summary ========
pass: 3/3 (1.0)
avg keyword score: 1.0
recall@4: 3/3 (1.0)
saved: .../hybrid_rerank_20260728_233918.json
```

**快速判断**：`pass` 和 `recall@k` 都接近 1.0 说明整体健康；有 `FAIL` 或 `R✗` 再往下挖。

中间夹杂的 JSON 日志（`retrieve.hybrid`、`generate.done` 等）是 pipeline 调试信息，**看结果时可以忽略**。

### 第二步：看 summary —— 判断「这轮配置行不行」

打开 `data/eval/results/<tag>_<时间戳>.json`，**先看文件头 5 个数**：

| 指标 | 评什么 | 理想值 | 掉了说明什么 |
|------|--------|--------|--------------|
| `pass_rate` | 端到端：答案 + 拒答 | 越高越好 | 有题答错或该拒没拒 |
| `avg_keyword_score` | 答案要点覆盖（偏生成） | 接近 1.0 | 回答缺关键词，即使 `pass_rate` 还行也要看 miss |
| `recall_at_k` | 检索是否找到对文档 | 越高越好 | top-k 没召回预期语料，优先改检索/分块 |
| `n` | 实际跑了多少题 | 全量约 30 | `--limit 3` 只是冒烟，不能当最终结论 |
| `retrieve` + `use_rerank` | 本轮用的配置 | — | 对照时必须确认，别拿不同配置比 |

**两个维度分开看**：`recall_at_k` 评检索，`pass_rate` / `avg_keyword_score` 评生成。  
常见模式：`recall` 低但 `pass` 还行 → 答案可能靠幻觉蒙对；`recall` 高但 `pass` 低 → 材料找到了，prompt/生成漏点。

### 第三步：看 items —— 定位「哪题、哪一环坏了」

只对 **FAIL** 或 **recall=R✗** 的题展开 `items[]`：

1. 看 `keyword_miss` → 答案缺哪些要点（对照 `answer` 和 golden 的 `must_contain`）
2. 看 `recall_miss` → 哪些预期文档没在 top-k 里（对照 `retrieved_sources`）
3. 看 `answer` → 实际说了什么，是漏写、写错还是不该答却答了

拒答题额外看 `refuse_ok`：库外题必须含「无法确认」。

### 第四步：三路对照 —— 改检索时选配置

跑 `compare.py` 后看终端表格和 `compare_latest.json`：

```
profile                  pass  keyword   recall@k
-------------------------------------------------
vector_norerank         1.000    1.000      1.000
hybrid_norerank         1.000    1.000      1.000
hybrid_rerank           1.000    1.000      1.000
```

**怎么读**：

- 三行数字一样 → 这轮改动对 eval 无影响（或样本太少 `--limit 3` 看不出差异）
- `recall@k`：hybrid > vector → 混合检索有帮助；hybrid+rerank > hybrid → 重排有帮助
- `pass` / `keyword` 升、recall 不变 → 生成侧或偶然性；recall 升、pass 不变 → 检索好了但生成还没用上材料

每行的 `result_file` 指向完整明细，某配置明显更好时再打开对应 JSON 看单题。

### 第五步：和上次比 —— 回归的意义

改代码前后各跑一轮全量 eval，对比**同 tag、同 k** 的两个 JSON：

- `pass_rate` 掉了 → **回归**，优先查 FAIL 的 `id`
- 只有 `recall_at_k` 掉了 → 检索退化
- 只有 `avg_keyword_score` 掉了 → 生成/prompt 退化

文件名里的时间戳（如 `20260728_233918`）用来区分先后；`compare_latest.json` 只保留最近一次三路对照。

### 你这次 `--limit 3` 的结果

当前三路对照 3/3 全满，说明**前 3 题**在 vector / hybrid / hybrid+rerank 下都通过——适合冒烟，**不能代表 30 题全量表现**。要下结论请跑：

```bash
uv run python tests/eval/compare.py
```

---

## 相关代码

| 文件 | 职责 |
|------|------|
| `scoring.py` | `score_answer()`、`score_recall()` 及去空格/同义组规则 |
| `run.py` | 读 golden → `retrieve_chunks` + `generate` → 打分 → 写 results |
| `compare.py` | 连续跑三种配置并生成 `compare_latest.json` |

业务检索入口：`src/rag_assistant/pipeline.py` 中的 `retrieve_chunks()`（与 `--query` 共用同一检索路径）。
