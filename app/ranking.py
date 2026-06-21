"""彙整每日 mentions → 討論度＋推薦度綜合分 → 取前 N。

  討論度  = 不重複來源數 × 2 + 總提及次數      （衡量「多熱」）
  推薦度  = (看多 − 看空) / 總提及次數          （衡量「多看好」，範圍 -1~1）
  綜合分  = 討論度(正規化 0-100) × W1 + 推薦度(正規化 0-100) × W2
"""
from __future__ import annotations

import logging

from app.config import TOP_N, WEIGHT_DISCUSSION, WEIGHT_RECOMMENDATION
from app.db import get_conn

log = logging.getLogger("ranking")


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-9:
        return {k: 50.0 for k in values}
    return {k: (v - lo) / (hi - lo) * 100 for k, v in values.items()}


def compute(item_date: str, top_n: int | None = None) -> list[dict]:
    top_n = top_n or TOP_N
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT ticker, name, source_name, sentiment FROM mentions WHERE item_date=?",
            (item_date,),
        ).fetchall()

    agg: dict[str, dict] = {}
    for r in rows:
        t = r["ticker"]
        a = agg.setdefault(
            t, {"name": r["name"], "sources": set(), "n": 0, "bull": 0, "bear": 0}
        )
        a["sources"].add(r["source_name"])
        a["n"] += 1
        if r["sentiment"] == "bullish":
            a["bull"] += 1
        elif r["sentiment"] == "bearish":
            a["bear"] += 1

    if not agg:
        log.warning("%s 沒有任何 mention", item_date)
        return []

    discussion = {t: len(a["sources"]) * 2 + a["n"] for t, a in agg.items()}
    recommendation = {
        t: ((a["bull"] - a["bear"]) / a["n"] if a["n"] else 0.0) for t, a in agg.items()
    }
    disc_n = _normalize(discussion)
    rec_n = _normalize(recommendation)

    ranked = []
    for t, a in agg.items():
        total = disc_n[t] * WEIGHT_DISCUSSION + rec_n[t] * WEIGHT_RECOMMENDATION
        ranked.append(
            {
                "ticker": t,
                "name": a["name"],
                "discussion_score": round(disc_n[t], 1),
                "recommendation_score": round(rec_n[t], 1),
                "total_score": round(total, 1),
                "n_mentions": a["n"],
                "n_sources": len(a["sources"]),
                "n_bull": a["bull"],
                "n_bear": a["bear"],
            }
        )
    ranked.sort(key=lambda x: x["total_score"], reverse=True)
    ranked = ranked[:top_n]
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def save(item_date: str, ranked: list[dict]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM daily_rankings WHERE item_date=?", (item_date,))
        conn.executemany(
            "INSERT INTO daily_rankings"
            "(item_date, rank, ticker, name, discussion_score, recommendation_score,"
            " total_score, n_mentions, n_sources, n_bull, n_bear, summary)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    item_date, r["rank"], r["ticker"], r["name"],
                    r["discussion_score"], r["recommendation_score"], r["total_score"],
                    r["n_mentions"], r["n_sources"], r["n_bull"], r["n_bear"],
                    r.get("summary"),
                )
                for r in ranked
            ],
        )
