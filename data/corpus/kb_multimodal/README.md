# 多模态知识库（kb_multimodal）

**事实源是 `images/` 下的 PNG**，不是手写图说。

入库路径（生产口径）：

```text
PNG → Vision 模型自动 caption（按 file_hash 缓存）→ Qdrant + OpenSearch
```

```bash
# .env 设置可用的 VISION_MODEL（OpenAI-compatible 多模态）
uv run python -m rag_assistant.pipeline --ingest --only kb_multimodal --reset
uv run python -m rag_assistant.pipeline --react --query "架构图里订单服务连到哪些下游？"
```

| 文件 | 内容 |
|------|------|
| `images/01-core-services-arch.png` | 核心服务架构图 |
| `images/02-release-board.png` | 发布窗口看板截图 |
| `images/03-onboarding-slide.png` | 入职幻灯第 3 页 |

工具：`search_visual`；Profile：`MULTIMODAL_PROFILE`。
