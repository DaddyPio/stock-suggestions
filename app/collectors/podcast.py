"""財經 Podcast 抓取（RSS shownotes / 標題）。

多數節目無逐字稿，僅能用標題＋節目簡介抽股，訊號較弱。
"""
from __future__ import annotations

import logging
from datetime import date

import feedparser
from bs4 import BeautifulSoup

from app.collectors.base import RawItem, within_lookback

log = logging.getLogger("collect.podcast")


def _entry_date(entry) -> date | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        try:
            return date(t.tm_year, t.tm_mon, t.tm_mday)
        except Exception:  # noqa: BLE001
            return None
    return None


def collect(feeds: list[dict], lookback_days: int) -> list[RawItem]:
    items: list[RawItem] = []
    for feed in feeds:
        name, url = feed.get("name", "podcast"), feed.get("url")
        if not url:
            continue
        try:
            parsed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            log.warning("Podcast %s 解析失敗：%s", name, e)
            continue
        for entry in parsed.entries:
            d = _entry_date(entry)
            if not within_lookback(d, lookback_days):
                continue
            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("subtitle", "")
            text = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)
            items.append(
                RawItem(
                    source_type="podcast",
                    source_name=name,
                    title=title,
                    content=f"{title}。{text[:3000]}",
                    url=entry.get("link", ""),
                    published_at=(d.isoformat() if d else ""),
                    item_date=(d.isoformat() if d else ""),
                )
            )
    return items
