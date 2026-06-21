"""抓取共用：資料結構、日期工具、彙整入口。"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("collect")

# 台灣時區
TW_TZ = timezone(timedelta(hours=8))


@dataclass
class RawItem:
    source_type: str          # news / ptt / dcard / youtube / podcast
    source_name: str
    title: str
    content: str
    url: str = ""
    published_at: str = ""     # ISO，盡力而為
    item_date: str = field(default="")  # 歸屬日 YYYY-MM-DD

    def hash(self) -> str:
        key = f"{self.source_type}|{self.url}|{self.title}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


def today_tw() -> date:
    return datetime.now(TW_TZ).date()


def within_lookback(d: date | None, lookback_days: int) -> bool:
    """內容是否落在「最近 lookback_days 天」內（含今天）。日期不明則放行。"""
    if d is None:
        return True
    return today_tw() - d <= timedelta(days=lookback_days)


def collect_all(sources: dict, lookback_days: int = 1) -> list[RawItem]:
    """依設定跑所有來源；任一來源拋錯都不影響其他來源。"""
    # 延遲匯入避免循環相依
    from app.collectors import dcard, news_rss, podcast, ptt, youtube

    items: list[RawItem] = []
    tasks = [
        ("news_rss", lambda: news_rss.collect(sources.get("news_rss", []), lookback_days)),
        ("ptt", lambda: ptt.collect(sources.get("ptt", {}), lookback_days)),
        ("dcard", lambda: dcard.collect(sources.get("dcard", {}), lookback_days)),
        ("youtube", lambda: youtube.collect(sources.get("youtube", {}), lookback_days)),
        ("podcast", lambda: podcast.collect(
            sources.get("podcast_rss", []), lookback_days, sources.get("whisper", {}))),
    ]
    for name, fn in tasks:
        try:
            got = fn()
            log.info("來源 %s：抓到 %d 筆", name, len(got))
            items.extend(got)
        except Exception as e:  # noqa: BLE001 一個來源掛掉不該拖垮整體
            log.warning("來源 %s 失敗，略過：%s", name, e)
    return items
