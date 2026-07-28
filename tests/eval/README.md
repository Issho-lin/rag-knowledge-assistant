# Eval 回归评测说明

本目录是 **golden set 回归评测**（集成测试），不是主业务代码。  
对固定题集跑「检索 → 生成 → 打分」，用来在改检索/分块/prompt 后做 before/after 对照。

```
data/eval/golden.json          考卷（题 + 断言，人维护）
tests/eval/run.py              跑一轮评测，写 results
tests/eval/compare.py          跑 vector / hybrid / hybrid+rerank 三路对照
tests/eval/scoring.py          纯打分逻辑（无 LLM）
data/eval/results/*.json       成绩单（程序生成）
```

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
