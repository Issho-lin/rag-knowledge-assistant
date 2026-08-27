"""图像 VLM caption：生产多模态入库的读图层。

事实源是图片；本模块只负责生成可检索文本，并按 file_hash 缓存。
caption 失败显式抛错，不静默回退手写文案。
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.config import get_settings
from ..core.logging import get_logger
from .fingerprint import content_hash

log = get_logger(__name__)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

_CAPTION_SYSTEM = """你是企业知识库的图像入库模块。根据图片生成可用于检索的中文结构化描述。
要求：
1. 只描述图上可见的信息，不要编造图外制度条文。
2. 使用 Markdown，包含这些小节（有则写）：
   # 标题
   ## 可见文字
   ## 节点与区块
   ## 连线或流程
   ## 读图要点
3. 「读图要点」用条目列出图上能直接回答的事实（实体名、时间窗口、步骤等）。
4. 输出纯 Markdown，不要包代码围栏。"""


class VisionCaptionError(RuntimeError):
    """VLM caption 失败；入库应中止该图像，不得用假文案顶替。"""


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTS


def _mime_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


def _cache_path(file_hash: str) -> Path:
    root = get_settings().vision_caption_cache_dir
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{file_hash}.json"


def _load_cache(file_hash: str) -> str | None:
    path = _cache_path(file_hash)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("file_hash") != file_hash:
        return None
    caption = str(data.get("caption") or "").strip()
    return caption or None


def _save_cache(file_hash: str, *, source: str, model: str, caption: str) -> None:
    path = _cache_path(file_hash)
    path.write_text(
        json.dumps(
            {
                "file_hash": file_hash,
                "source": source,
                "model": model,
                "caption": caption,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _vision_llm() -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=s.vision_model,
        timeout=s.llm_timeout_seconds,
        max_retries=0,
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
    )


def caption_image(path: Path, *, use_cache: bool = True) -> str:
    """对单张图片调用 Vision 模型生成 caption；命中缓存则跳过 LLM。"""
    path = Path(path)
    if not path.is_file():
        raise VisionCaptionError(f"图像不存在: {path}")
    if not is_image_path(path):
        raise VisionCaptionError(f"不支持的图像类型: {path.suffix}")

    raw = path.read_bytes()
    file_hash = content_hash(str(path))
    if use_cache:
        cached = _load_cache(file_hash)
        if cached:
            log.info("vision.caption_cache_hit", source=str(path), hash=file_hash[:12])
            return cached

    s = get_settings()
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{_mime_for(path)};base64,{b64}"
    messages = [
        SystemMessage(content=_CAPTION_SYSTEM),
        HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        f"请描述这张企业知识库图像。文件名：{path.name}\n"
                        "输出结构化中文 Markdown caption。"
                    ),
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        ),
    ]

    try:
        resp = _vision_llm().invoke(messages)
    except Exception as exc:  # noqa: BLE001 — 统一成显式失败
        # 尽量区分可重试；无论哪种都不得静默吞掉
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        log.error(
            "vision.caption_failed",
            source=str(path),
            model=s.vision_model,
            status=status,
            error=str(exc),
        )
        raise VisionCaptionError(
            f"VLM caption 失败 source={path} model={s.vision_model}: {exc}"
        ) from exc

    caption = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    if not caption:
        raise VisionCaptionError(f"VLM 返回空 caption: {path}")

    _save_cache(file_hash, source=str(path), model=s.vision_model, caption=caption)
    log.info(
        "vision.caption_done",
        source=str(path),
        model=s.vision_model,
        chars=len(caption),
        hash=file_hash[:12],
    )
    return caption
