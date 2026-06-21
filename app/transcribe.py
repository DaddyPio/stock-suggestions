"""Podcast 純音檔語音轉錄（faster-whisper，CPU，免費）。

只對 sources.yml 中標記 transcribe: true 的節目（如股癌）做轉錄。
結果快取在 data/cache/transcripts/，避免重複轉錄同一集。
"""
from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path

import requests

from app.config import CACHE_DIR, USER_AGENT

log = logging.getLogger("transcribe")

TRANSCRIPT_CACHE = CACHE_DIR / "transcripts"
TRANSCRIPT_CACHE.mkdir(parents=True, exist_ok=True)

_MODEL = None  # 延遲載入的單例


def _get_model(model_size: str):
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        log.info("載入 Whisper 模型：%s（首次會下載）", model_size)
        _MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODEL


def _cache_path(key: str) -> Path:
    return TRANSCRIPT_CACHE / (hashlib.sha256(key.encode()).hexdigest() + ".txt")


def _download_audio(url: str) -> Path | None:
    try:
        suffix = ".mp3"
        tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
        with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
        return tmp
    except Exception as e:  # noqa: BLE001
        log.warning("下載音檔失敗 %s：%s", url, e)
        return None


def transcribe_audio(audio_url: str, cache_key: str, model_size: str, language: str) -> str:
    """轉錄單一音檔；有快取直接回快取。失敗回空字串。"""
    cache = _cache_path(cache_key)
    if cache.exists():
        return cache.read_text(encoding="utf-8")

    path = _download_audio(audio_url)
    if not path:
        return ""
    try:
        model = _get_model(model_size)
        segments, _info = model.transcribe(str(path), language=language, vad_filter=True)
        text = "".join(seg.text for seg in segments).strip()
        cache.write_text(text, encoding="utf-8")
        log.info("轉錄完成：%d 字（%s）", len(text), cache_key[:40])
        return text
    except Exception as e:  # noqa: BLE001
        log.warning("轉錄失敗 %s：%s", cache_key[:40], e)
        return ""
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
