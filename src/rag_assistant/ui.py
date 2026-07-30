"""Gradio 最小 Web 界面：多轮问答 + 检索详情侧栏。

用法（需先入库）：
    uv sync --extra ui
    uv run python -m rag_assistant.ui
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from .conversation import ChatTurn
from .logging import configure_logging, get_logger

if TYPE_CHECKING:
    from .pipeline import QueryResult

log = get_logger(__name__)


def format_result_detail(result: QueryResult) -> str:
    """侧栏 Markdown：改写问句、拒答原因、参考来源。"""
    parts: list[str] = []
    if result.rewritten_query:
        parts.append(f"**检索问句**：{result.rewritten_query}")
    note = result.refusal_note()
    if note:
        parts.append(f"**拒答**：{note}")
    if result.chunks:
        parts.append("**检索片段**")
        for i, c in enumerate(result.chunks, 1):
            src = c.get("source", "?").rsplit("/", 1)[-1]
            score = float(c.get("score", 0.0))
            preview = c.get("text", "").replace("\n", " ").strip()[:200]
            parts.append(f"- `[{i}]` {src} (score={score:.3f})\n  {preview}…")
    if result.citations:
        block = result.sources_text().strip()
        if block:
            parts.append(block)
    return "\n\n".join(parts) if parts else "_本轮无额外检索信息_"


def _turns_from_state(items: list[dict] | None) -> list[ChatTurn]:
    if not items:
        return []
    return [ChatTurn(role=t["role"], content=t["content"]) for t in items]


def _turns_to_state(turns: list[ChatTurn]) -> list[dict]:
    return [{"role": t.role, "content": t.content} for t in turns]


def _chat_respond(
    message: str,
    chat_history: list[dict] | None,
    turn_history_raw: list[dict] | None,
    *,
    k: int,
    retrieve: str,
    use_rerank: bool | None,
) -> tuple[list[dict], list[dict], str]:
    """Gradio 回调：调用 pipeline.query 并更新会话状态。"""
    from .pipeline import QueryResult, query

    chat_history = chat_history or []
    turn_history = _turns_from_state(turn_history_raw)
    message = (message or "").strip()
    if not message:
        return chat_history, _turns_to_state(turn_history), format_result_detail(
            QueryResult(answer="", chunks=[], citations=[])
        )

    result = query(
        message,
        k=k,
        history=turn_history,
        retrieve=retrieve,
        use_rerank=use_rerank,
    )
    turn_history = [
        *turn_history,
        ChatTurn(role="user", content=message),
        ChatTurn(role="assistant", content=result.answer),
    ]
    chat_history = [
        *chat_history,
        {"role": "user", "content": message},
        {"role": "assistant", "content": result.answer},
    ]
    detail = format_result_detail(result)
    log.info("ui.chat", refused=result.refused, rewritten=bool(result.rewritten_query))
    return chat_history, _turns_to_state(turn_history), detail


def build_demo(
    *,
    k: int = 4,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
):
    """构建 Gradio Blocks 应用（便于测试与 launch）。"""
    import gradio as gr

    with gr.Blocks(title="星云科技内部知识助手") as demo:
        # 必须在 Blocks 内创建，否则 Gradio 6 会 KeyError: 0
        turn_state = gr.State(value=[])
        gr.Markdown(
            "# 星云科技内部知识助手\n"
            "基于内部制度 / FAQ / SOP 的 RAG 问答。支持多轮追问；右侧展示检索问句与命中片段。"
        )
        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="对话",
                    height=480,
                )
                with gr.Row():
                    msg = gr.Textbox(
                        label="输入问题",
                        placeholder="例如：年假有多少天？",
                        scale=4,
                        show_label=False,
                    )
                    send = gr.Button("发送", variant="primary", scale=1)
                clear = gr.Button("清空对话")
            with gr.Column(scale=2):
                detail = gr.Markdown(
                    value="_提交问题后，这里显示检索问句、片段与来源。_",
                    label="检索详情",
                )

        inputs = [msg, chatbot, turn_state]
        outputs = [chatbot, turn_state, detail]

        respond = lambda m, h, t: _chat_respond(
            m, h, t, k=k, retrieve=retrieve, use_rerank=use_rerank
        )
        send.click(respond, inputs, outputs).then(lambda: "", None, msg)
        msg.submit(respond, inputs, outputs).then(lambda: "", None, msg)

        def _clear():
            return [], [], "_已清空对话_"

        clear.click(_clear, None, outputs)

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="星云科技内部知识助手 — Gradio 界面")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=7860, help="端口")
    parser.add_argument(
        "--inbrowser",
        action="store_true",
        default=True,
        help="启动后自动打开浏览器（默认开启）",
    )
    parser.add_argument(
        "--no-inbrowser",
        dest="inbrowser",
        action="store_false",
        help="不自动打开浏览器",
    )
    parser.add_argument("--share", action="store_true", help="生成公网临时链接")
    parser.add_argument("--k", type=int, default=4, help="检索 chunk 数")
    parser.add_argument(
        "--retrieve",
        choices=("hybrid", "vector"),
        default="hybrid",
        help="检索模式",
    )
    parser.add_argument(
        "--rerank",
        dest="use_rerank",
        action="store_true",
        default=None,
        help="启用重排",
    )
    parser.add_argument(
        "--no-rerank",
        dest="use_rerank",
        action="store_false",
        help="关闭重排",
    )
    args = parser.parse_args()
    configure_logging()

    print("正在加载 Gradio 界面（首次可能需 10–30 秒，请稍候）…", flush=True)
    demo = build_demo(k=args.k, retrieve=args.retrieve, use_rerank=args.use_rerank)
    url = f"http://{args.host}:{args.port}"
    print(f"启动 Web 服务：{url}", flush=True)
    try:
        demo.launch(
            server_name=args.host,
            server_port=args.port,
            share=args.share,
            inbrowser=args.inbrowser,
            show_error=True,
        )
    except OSError as exc:
        if "empty port" in str(exc).lower() or "address already in use" in str(exc).lower():
            print(
                f"\n端口 {args.port} 已被占用（可能已有一个 ui 在后台运行）。\n"
                f"  1. 关掉旧进程，或\n"
                f"  2. 换端口：uv run python -m rag_assistant.ui --port 7861\n"
                f"  3. 若已在运行，直接打开：{url}",
                file=sys.stderr,
                flush=True,
            )
        raise


if __name__ == "__main__":
    main()
