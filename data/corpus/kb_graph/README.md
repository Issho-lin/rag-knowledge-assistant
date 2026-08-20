# 星云科技 · 关系语料（虚构）

本目录只供给 **Graph RAG / Neo4j**（`--ingest-graph`），**不写入** Qdrant / OpenSearch。

| 文件 | 抽什么 |
|------|--------|
| `12-组织架构与汇报线.md` | Person `REPORTS_TO` |
| `13-系统依赖与服务清单.md` | Service `DEPENDS_ON` |
| `14-费用报销审批链.md` | Step `NEXT` |

人员节点与 `internal/csv/员工通讯录-摘录.csv` 对齐（工号 + 姓名）。
