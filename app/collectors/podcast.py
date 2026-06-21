"""財經 Podcast 抓取（RSS shownotes / 標題；可選語音轉錄）。

預設用標題＋節目簡介抽股；標記 transcribe: true 的節目（如股癌）
會下載音檔用 faster-whisper 轉錄，取得完整內容。
"""
from __future__ import annotations

import logging
from datetime import date

import feedparser
from bs4 import BeautifulSoup

from app.collectors.base import RawItem, within_lookback

log = logging.getLogger("collect.podcast")


def _enclosure_url(entry) -> str:
    for enc in entry.get("enclosures", []) or []:
        href = enc.get("href") or enc.get("url")
        if href:
            return href
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            return link["href"]
    return ""


def _entry_date(entry) -> date | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        try:
            return date(t.tm_year, t.tm_mon, t.tm_mday)
        except Exception:  # noqa: BLE001
            return None
    return None


def collect(feeds: list[dict], lookback_days: int, whisper: dict | None = None) -> list[RawItem]:
    whisper = whisper or {}
    w_model = whisper.get("model", "base")
    w_lang = whisper.get("language", "zh")
    w_max = int(whisper.get("max_episodes_per_feed", 1))

    items: list[RawItem] = []
    for feed in feeds:
        name, url = feed.get("name", "podcast"), feed.get("url")
        do_transcribe = bool(feed.get("transcribe", False))
        if not url:
            continue
        try:
            parsed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            log.warning("Podcast %s 解析失敗：%s", name, e)
            continue

        transcribed = 0
        for entry in parsed.entries:
            d = _entry_date(entry)
            if not within_lookback(d, lookback_days):
                continue
            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("subtitle", "")
            text = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)
            content = f"{title}。{text[:3000]}"

            # 標記轉錄的節目：下載音檔轉逐字稿（每 feed 限 w_max 集，避免逾時）
            if do_transcribe and transcribed < w_max:
                audio = _enclosure_url(entry)
                if audio:
                    from app.transcribe import transcribe_audio

                    key = entry.get("id") or entry.get("link") or audio
                    log.info("轉錄 %s：%s", name, title[:40])
                    tx = transcribe_audio(audio, key, w_model, w_lang)
                    if tx:
                        content = f"{title}。{tx}"
                        transcribed += 1

            items.append(
                RawItem(
                    source_type="podcast",
                    source_name=name,
                    title=title,
                    content=content,
                    url=entry.get("link", ""),
                    published_at=(d.isoformat() if d else ""),
                    item_date=(d.isoformat() if d else ""),
                )
            )
    return items
