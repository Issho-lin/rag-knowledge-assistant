"""Vision caption：缓存命中与失败显式抛错。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rag_assistant.ingest.vision_caption import (
    VisionCaptionError,
    caption_image,
    is_image_path,
)


def test_is_image_path():
    assert is_image_path(Path("a.png"))
    assert is_image_path(Path("b.JPG"))
    assert not is_image_path(Path("c.md"))


def test_caption_image_cache_hit(tmp_path, monkeypatch):
    img = tmp_path / "arch.png"
    img.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00"
        b"\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("VISION_CAPTION_CACHE_DIR", str(cache_dir))
    # 重置 settings 单例
    import rag_assistant.core.config as cfg

    cfg._settings = None

    from rag_assistant.ingest.fingerprint import content_hash

    h = content_hash(str(img))
    cache_dir.mkdir(parents=True)
    (cache_dir / f"{h}.json").write_text(
        json.dumps({"file_hash": h, "source": str(img), "model": "x", "caption": "缓存标题"}),
        encoding="utf-8",
    )

    with patch("rag_assistant.ingest.vision_caption._vision_llm") as mock_llm:
        text = caption_image(img)
        mock_llm.assert_not_called()
    assert text == "缓存标题"
    cfg._settings = None


def test_caption_image_llm_failure_is_explicit(tmp_path, monkeypatch):
    img = tmp_path / "board.png"
    img.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00"
        b"\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    cache_dir = tmp_path / "cache2"
    monkeypatch.setenv("VISION_CAPTION_CACHE_DIR", str(cache_dir))
    import rag_assistant.core.config as cfg

    cfg._settings = None

    mock_model = MagicMock()
    mock_model.invoke.side_effect = RuntimeError("vision down")
    with patch("rag_assistant.ingest.vision_caption._vision_llm", return_value=mock_model):
        with pytest.raises(VisionCaptionError, match="VLM caption 失败"):
            caption_image(img, use_cache=False)
    cfg._settings = None


def test_format_observation_shows_media_path():
    from rag_assistant.kb.search import format_chunks_observation

    text = format_chunks_observation(
        [
            {
                "source": "data/corpus/kb_multimodal/images/01-core-services-arch.png",
                "score": 0.9,
                "text": "订单服务 → 支付服务",
                "kind": "image",
                "media_path": "data/corpus/kb_multimodal/images/01-core-services-arch.png",
            }
        ],
        kb_id="multimodal",
    )
    assert "media=" in text
    assert "01-core-services-arch.png" in text
