"""對前 N 檔個股，彙整當日相關內容寫成 ~500 字繁體中文摘要。"""
from __future__ import annotations

import logging

from app.config import ANTHROPIC_API_KEY, SUMMARY_MODEL
from app.db import get_conn

log = logging.getLogger("summarize")

MAX_SNIPPETS = 40

SYSTEM = (
    "你是專業台股研究員，根據當日各方輿情（新聞、論壇、YouTube 財經頻道、Podcast）"
    "為單一個股撰寫約 500 字的繁體中文摘要。內容需涵蓋：被討論的主要原因/題材、"
    "市場看多與看空的理由、值得注意的風險。語氣客觀，不做投資建議與買賣指令。"
    "直接輸出摘要本文，不要標題或開場白。"
)


def _gather(item_date: str, ticker: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT source_type, source_name, snippet, sentiment FROM mentions "
            "WHERE item_date=? AND ticker=? ORDER BY sentiment",
            (item_date, ticker),
        ).fetchall()
    return [dict(r) for r in rows][:MAX_SNIPPETS]


def _summarize_one(client, name: str, ticker: str, snippets: list[dict]) -> str:
    bundle = "\n".join(
        f'[{s["source_type"]}/{s["source_name"]}|{s["sentiment"]}] {s["snippet"]}'
        for s in snippets
    )
    prompt = (
        f"個股：{name}（{ticker}）\n"
        f"當日相關輿情片段（共 {len(snippets)} 則，標註來源與情緒）：\n\n{bundle}\n\n"
        "請寫約 500 字摘要。"
    )
    resp = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=1200,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def summarize_top(item_date: str, ranked: list[dict]) -> list[dict]:
    """逐檔產生摘要，寫回 ranked 與 daily_rankings。"""
    if not ANTHROPIC_API_KEY:
        log.warning("未設定 ANTHROPIC_API_KEY，跳過摘要")
        for r in ranked:
            r["summary"] = "（未設定 ANTHROPIC_API_KEY，無法產生摘要）"
        _save_summaries(item_date, ranked)
        return ranked

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    for r in ranked:
        snippets = _gather(item_date, r["ticker"])
        try:
            r["summary"] = _summarize_one(client, r["name"], r["ticker"], snippets)
        except Exception as e:  # noqa: BLE001
            log.warning("%s 摘要失敗：%s", r["ticker"], e)
            r["summary"] = "（摘要產生失敗）"
    _save_summaries(item_date, ranked)
    return ranked


def _save_summaries(item_date: str, ranked: list[dict]) -> None:
    with get_conn() as conn:
        conn.executemany(
            "UPDATE daily_rankings SET summary=? WHERE item_date=? AND ticker=?",
            [(r["summary"], item_date, r["ticker"]) for r in ranked],
        )
