"""YouTube 財經頻道抓取。

流程：handle → channel_id → 頻道 RSS（最新影片）→ 中文自動字幕。
取不到字幕的影片，退而用標題＋影片簡介。
"""
from __future__ import annotations

import logging
import re
from datetime import date

import feedparser
import requests

from app.collectors.base import RawItem, within_lookback
from app.config import USER_AGENT

log = logging.getLogger("collect.youtube")

CHANNEL_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"


def _resolve_channel_id(handle: str) -> str | None:
    """從 https://www.youtube.com/@handle 頁面解析 channelId。"""
    handle = handle.lstrip("@")
    try:
        r = requests.get(
            f"https://www.youtube.com/@{handle}",
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("YouTube handle %s 解析失敗：%s", handle, e)
        return None
    m = re.search(r'"channelId":"(UC[\w-]+)"', r.text)
    if not m:
        m = re.search(r'"externalId":"(UC[\w-]+)"', r.text)
    return m.group(1) if m else None


def _transcript(video_id: str) -> str:
    """抓中文自動字幕；取不到回空字串。"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        # 新版 API：list() 取得可用字幕，挑中文
        try:
            transcripts = api.list(video_id)
            for langs in (["zh-TW", "zh-Hant"], ["zh", "zh-Hans", "zh-CN"]):
                try:
                    fetched = transcripts.find_transcript(langs).fetch()
                    return " ".join(s.text for s in fetched)
                except Exception:  # noqa: BLE001
                    continue
        except AttributeError:
            # 舊版 API fallback
            fetched = YouTubeTranscriptApi.get_transcript(
                video_id, languages=["zh-TW", "zh-Hant", "zh", "zh-Hans"]
            )
            return " ".join(s["text"] for s in fetched)
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _entry_date(entry) -> date | None:
    t = entry.get("published_parsed")
    if t:
        try:
            return date(t.tm_year, t.tm_mon, t.tm_mday)
        except Exception:  # noqa: BLE001
            return None
    return None


def collect(cfg: dict, lookback_days: int) -> list[RawItem]:
    if not cfg:
        return []
    channels = cfg.get("channels", [])
    max_videos = int(cfg.get("max_videos_per_channel", 3))

    items: list[RawItem] = []
    for ch in channels:
        name = ch.get("name", "YouTube")
        cid = ch.get("channel_id")
        if not cid and ch.get("handle"):
            cid = _resolve_channel_id(ch["handle"])
        if not cid:
            log.warning("頻道 %s 無 channel_id，略過", name)
            continue
        try:
            parsed = feedparser.parse(CHANNEL_RSS.format(cid=cid))
        except Exception as e:  # noqa: BLE001
            log.warning("頻道 %s RSS 失敗：%s", name, e)
            continue

        count = 0
        for entry in parsed.entries:
            if count >= max_videos:
                break
            d = _entry_date(entry)
            if not within_lookback(d, lookback_days):
                continue
            vid = entry.get("yt_videoid") or entry.get("link", "").split("v=")[-1]
            title = entry.get("title", "")
            desc = ""
            if entry.get("summary"):
                desc = entry["summary"]
            transcript = _transcript(vid) if vid else ""
            body = transcript or desc
            content = f"{title}。{body[:6000]}"
            items.append(
                RawItem(
                    source_type="youtube",
                    source_name=name,
                    title=title,
                    content=content,
                    url=entry.get("link", ""),
                    published_at=(d.isoformat() if d else ""),
                    item_date=(d.isoformat() if d else ""),
                )
            )
            count += 1
    return items
