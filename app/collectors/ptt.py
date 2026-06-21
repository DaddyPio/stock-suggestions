"""PTT 看板抓取（網頁版，需 over18 cookie）。

預設抓 Stock 版最近幾頁的文章標題與內文。失敗（被擋/改版）會略過。
"""
from __future__ import annotations

import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from app.collectors.base import RawItem, within_lookback
from app.config import USER_AGENT

log = logging.getLogger("collect.ptt")

BASE = "https://www.ptt.cc"
COOKIES = {"over18": "1"}


def _get(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, cookies=COOKIES, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:  # noqa: BLE001
        log.warning("PTT 取得失敗 %s：%s", url, e)
        return None


def _index_urls(board: str, pages: int) -> list[str]:
    """從最新一頁往回推 pages 頁。"""
    html = _get(f"{BASE}/bbs/{board}/index.html")
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    urls = [f"{BASE}/bbs/{board}/index.html"]
    # 「上頁」連結含目前頁碼
    prev = soup.select_one("a.btn.wide:-soup-contains('上頁')")
    if not prev:
        for a in soup.select("a.btn.wide"):
            if "上頁" in a.get_text():
                prev = a
                break
    if prev and prev.get("href"):
        m = re.search(r"index(\d+)\.html", prev["href"])
        if m:
            latest = int(m.group(1))  # 上頁編號 = 最新頁 - 1
            for i in range(latest, latest - (pages - 1), -1):
                if i > 0:
                    urls.append(f"{BASE}/bbs/{board}/index{i}.html")
    return urls


def _article_links(index_html: str, board: str) -> list[str]:
    soup = BeautifulSoup(index_html, "lxml")
    links = []
    for div in soup.select("div.r-ent div.title a"):
        href = div.get("href")
        if href:
            links.append(BASE + href)
    return links


def _parse_article(html: str) -> tuple[str, str, date | None]:
    soup = BeautifulSoup(html, "lxml")
    title, post_date = "", None
    for meta in soup.select("div.article-metaline"):
        tag = meta.select_one(".article-meta-tag")
        val = meta.select_one(".article-meta-value")
        if not tag or not val:
            continue
        if "標題" in tag.get_text():
            title = val.get_text(strip=True)
        elif "時間" in tag.get_text():
            try:
                # 例：Sat Jun 21 09:12:33 2026
                from datetime import datetime

                post_date = datetime.strptime(val.get_text(strip=True), "%a %b %d %H:%M:%S %Y").date()
            except Exception:  # noqa: BLE001
                pass
    main = soup.select_one("#main-content")
    body = main.get_text("\n", strip=True) if main else ""
    # 砍掉推文區（從第一個 span.push 之後）
    body = re.split(r"※ 發信站", body)[0]
    return title, body, post_date


def collect(cfg: dict, lookback_days: int) -> list[RawItem]:
    if not cfg or not cfg.get("enabled", False):
        return []
    board = cfg.get("board", "Stock")
    pages = int(cfg.get("pages", 2))

    items: list[RawItem] = []
    for index_url in _index_urls(board, pages):
        index_html = _get(index_url)
        if not index_html:
            continue
        for link in _article_links(index_html, board):
            html = _get(link)
            if not html:
                continue
            title, body, post_date = _parse_article(html)
            if not within_lookback(post_date, lookback_days):
                continue
            if not title:
                continue
            items.append(
                RawItem(
                    source_type="ptt",
                    source_name=f"PTT/{board}",
                    title=title,
                    content=f"{title}。{body[:2000]}",
                    url=link,
                    published_at=(post_date.isoformat() if post_date else ""),
                    item_date=(post_date.isoformat() if post_date else ""),
                )
            )
    return items
