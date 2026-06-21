"""新聞 / 評論 RSS 抓取（feedparser）。"""
from __future__ import annotations

import logging
from datetime import date

import feedparser

from app.collectors.base import RawItem, within_lookback

log = logging.getLogger("collect.news")


def _entry_date(entry) -> date | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return date(t.tm_year, t.tm_mon, t.tm_mday)
            except Exception:  # noqa: BLE001
                pass
    return None


def collect(feeds: list[dict], lookback_days: int) -> list[RawItem]:
    items: list[RawItem] = []
    for feed in feeds:
        name, url = feed.get("name", "news"), feed.get("url")
        if not url:
            continue
        try:
            parsed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            log.warning("RSS %s 解析失敗：%s", name, e)
            continue
        if parsed.bozo and not parsed.entries:
            log.warning("RSS %s 無內容（bozo）", name)
            continue
        for entry in parsed.entries:
            d = _entry_date(entry)
            if not within_lookback(d, lookback_days):
                continue
            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            # 去 HTML 標籤
            from bs4 import BeautifulSoup

            text = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)
            items.append(
                RawItem(
                    source_type="news",
                    source_name=name,
                    title=title,
                    content=f"{title}。{text}",
                    url=entry.get("link", ""),
                    published_at=(d.isoformat() if d else ""),
                    item_date=(d.isoformat() if d else ""),
                )
            )
    return items
