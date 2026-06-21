"""把抓到的 RawItem 入庫並抽出個股提及。"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from app.collectors.base import RawItem
from app.db import get_conn
from app.universe import StockMatcher

log = logging.getLogger("extract")

SNIPPET_RADIUS = 120


def _snippet(text: str, ticker: str, name: str) -> str:
    """取個股出現處前後文，給情緒/摘要當依據。"""
    idx = text.find(name)
    if idx < 0:
        m = re.search(rf"(?<!\d){ticker}(?!\d)", text)
        idx = m.start() if m else 0
    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(text), idx + SNIPPET_RADIUS)
    return text[start:end].replace("\n", " ").strip()


def persist_and_extract(items: list[RawItem], matcher: StockMatcher) -> int:
    """入庫 raw_items（去重）並產生 mentions。回傳新增 mention 數。"""
    now = datetime.now().isoformat(timespec="seconds")
    n_mentions = 0
    with get_conn() as conn:
        for item in items:
            h = item.hash()
            cur = conn.execute(
                "INSERT OR IGNORE INTO raw_items"
                "(source_type, source_name, url, title, content, published_at, fetched_at, item_date, hash)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    item.source_type, item.source_name, item.url, item.title,
                    item.content, item.published_at, now, item.item_date, h,
                ),
            )
            if cur.rowcount == 0:
                continue  # 重複內容
            raw_id = cur.lastrowid

            tickers = matcher.find(item.content)
            for t in tickers:
                name = matcher.name_of(t)
                conn.execute(
                    "INSERT INTO mentions"
                    "(raw_item_id, ticker, name, source_type, source_name, snippet, sentiment, item_date)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        raw_id, t, name, item.source_type, item.source_name,
                        _snippet(item.content, t, name), None, item.item_date,
                    ),
                )
                n_mentions += 1
    return n_mentions
