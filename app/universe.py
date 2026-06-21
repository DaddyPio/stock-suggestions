"""股票字典：從 TWSE/TPEx 官方 ISIN 清單抓上市＋上櫃普通股，
存進 stocks 表，並提供「文本 → 個股提及」的抽取器。

抽股完全用字典比對，不呼叫 LLM：零成本、零幻覺。
"""
from __future__ import annotations

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.config import USER_AGENT
from app.db import get_conn

# strMode=2 上市、strMode=4 上櫃
ISIN_URLS = {
    "上市": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
    "上櫃": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
}


def sync_universe() -> int:
    """下載官方清單，更新 stocks 表。回傳筆數。"""
    rows: list[tuple[str, str, str]] = []
    for market, url in ISIN_URLS.items():
        rows.extend(_parse_isin(url, market))

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO stocks(ticker, name, market, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, "
            "market=excluded.market, updated_at=excluded.updated_at",
            [(t, n, m, now) for t, n, m in rows],
        )
    return len(rows)


def _parse_isin(url: str, market: str) -> list[tuple[str, str, str]]:
    """解析 ISIN 頁面。只取『股票』類（4 碼普通股）。"""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.encoding = "big5"
    soup = BeautifulSoup(resp.text, "lxml")

    out: list[tuple[str, str, str]] = []
    current_category = ""
    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        # 分類標頭列（如「股票」「上市認購(售)權證」）只有一格且 colspan
        if len(tds) == 1:
            current_category = tds[0].get_text(strip=True)
            continue
        if len(tds) < 4:
            continue
        if "股票" not in current_category:
            continue
        # 第一格格式："2330　台積電"（中間是全形空白 　）
        first = tds[0].get_text(strip=True).replace("\xa0", " ")
        parts = re.split(r"[　 ]+", first, maxsplit=1)
        if len(parts) != 2:
            continue
        ticker, name = parts[0].strip(), parts[1].strip()
        if re.fullmatch(r"\d{4}", ticker) and name:
            out.append((ticker, name, market))
    return out


# --------------------------------------------------------------------------
# 抽取器
# --------------------------------------------------------------------------
class StockMatcher:
    """把一段文字比對出提到的個股。

    比對規則：
      - 命中「公司全名」（>=2 字）→ 採用
      - 命中 4 碼「股票代號」且前後非數字 → 採用
      - ambiguous_names 中的簡稱不用名稱命中（避免日常用語誤判），
        但仍可被代號命中
    """

    def __init__(self, ambiguous_names: list[str] | None = None):
        self.ambiguous = set(ambiguous_names or [])
        self.ticker_to_name: dict[str, str] = {}
        self.name_to_ticker: dict[str, str] = {}
        self._name_re: re.Pattern | None = None
        self._ticker_re = re.compile(r"(?<!\d)(\d{4})(?!\d)")

    def load(self) -> "StockMatcher":
        with get_conn() as conn:
            rows = conn.execute("SELECT ticker, name FROM stocks").fetchall()
        for r in rows:
            self.ticker_to_name[r["ticker"]] = r["name"]
            self.name_to_ticker[r["name"]] = r["ticker"]
        # 長名優先比對，避免「台積電」被「台積」之類截斷
        names = sorted(
            (n for n in self.name_to_ticker if n not in self.ambiguous and len(n) >= 2),
            key=len,
            reverse=True,
        )
        if names:
            self._name_re = re.compile("|".join(re.escape(n) for n in names))
        return self

    def find(self, text: str) -> set[str]:
        """回傳命中的 ticker 集合。"""
        if not text:
            return set()
        hits: set[str] = set()
        if self._name_re:
            for m in self._name_re.finditer(text):
                hits.add(self.name_to_ticker[m.group(0)])
        for m in self._ticker_re.finditer(text):
            t = m.group(1)
            if t in self.ticker_to_name:
                hits.add(t)
        return hits

    def name_of(self, ticker: str) -> str:
        return self.ticker_to_name.get(ticker, ticker)

    def count(self) -> int:
        return len(self.ticker_to_name)
