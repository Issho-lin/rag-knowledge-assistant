# PDF 知识库（kb_pdf）

将 PDF 手册放入 `pdf/` 子目录，执行 `uv run python -m rag_assistant.pipeline --ingest --reset`。

## 示例语料

| 文件 | 主题 | 约字数 |
|------|------|--------|
| `10-办公设备操作手册.pdf` | 打印机、会议室、门禁、笔记本、网络 | ~1900 |
| `11-园区设施与后勤服务手册.pdf` | 停车、餐厅、健身、消防、班车、失物招领 | **3000+** |

内容与 `internal/` 制度语料不重复，专用于 `kb=pdf` 检索实验。

重新生成：

```bash
uv run --with reportlab python scripts/gen_pdf_corpus.py          # 全部
uv run --with reportlab python scripts/gen_pdf_corpus.py --only 11  # 仅园区手册
uv run python -m rag_assistant.pipeline --ingest --reset
```

## 检索示例

```bash
uv run python -m rag_assistant.pipeline --query "打印机卡纸怎么办" --kb pdf
uv run python -m rag_assistant.pipeline --query "地下停车场固定车位怎么申请" --kb pdf
uv run python -m rag_assistant.pipeline --query "健身房开放时间" --kb pdf
uv run python -m rag_assistant.pipeline --query "年假有多少天" --kb pdf   # 应不在 pdf 库
```

切块策略：固定窗口 800 字（见 `src/rag_assistant/kb/profiles.py` 中 `PDF_PROFILE`）。
