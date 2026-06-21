"""Dcard 股票版抓取（公開 API）。

Dcard 偶有 Cloudflare 防護，失敗即略過（輔助來源）。
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import requests

from app.collectors.base import RawItem, within_lookback
from app.config import USER_AGENT

log = logging.getLogger("collect.dcard")

API = "https://www.dcard.tw/service/api/v2/forums/{forum}/posts"


def _post_detail(post_id: int) -> str:
    try:
        r = requests.get(
            f"https://www.dcard.tw/service/api/v2/posts/{post_id}",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("content", "")
    except Exception:  # noqa: BLE001
        return ""


def _parse_date(s: str) -> date | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:  # noqa: BLE001
        return None


def collect(cfg: dict, lookback_days: int) -> list[RawItem]:
    if not cfg or not cfg.get("enabled", False):
        return []
    forum = cfg.get("forum", "stock")
    limit = int(cfg.get("limit", 30))

    try:
        r = requests.get(
            API.format(forum=forum),
            params={"popular": "false", "limit": limit},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=20,
        )
        r.raise_for_status()
        posts = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("Dcard API 失敗：%s", e)
        return []

    items: list[RawItem] = []
    for p in posts:
        d = _parse_date(p.get("createdAt", ""))
        if not within_lookback(d, lookback_days):
            continue
        title = p.get("title", "")
        excerpt = p.get("excerpt", "")
        body = _post_detail(p.get("id")) or excerpt
        items.append(
            RawItem(
                source_type="dcard",
                source_name=f"Dcard/{forum}",
                title=title,
                content=f"{title}。{body[:2000]}",
                url=f"https://www.dcard.tw/f/{forum}/p/{p.get('id')}",
                published_at=(d.isoformat() if d else ""),
                item_date=(d.isoformat() if d else ""),
            )
        )
    return items
