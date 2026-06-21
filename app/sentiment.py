"""對 mentions 做情緒判斷（看多 / 看空 / 中性），用便宜模型批次處理。"""
from __future__ import annotations

import json
import logging

from app.config import ANTHROPIC_API_KEY, SENTIMENT_MODEL
from app.db import get_conn

log = logging.getLogger("sentiment")

BATCH = 25
VALID = {"bullish", "bearish", "neutral"}

SYSTEM = (
    "你是台股輿情分析助手。會收到多則『提到某檔個股的文字片段』，"
    "判斷每則對『該檔個股』的態度：看多(bullish)、看空(bearish)、或中性/無明確方向(neutral)。"
    "只看對該股的觀點，不是整體大盤。嚴格只輸出 JSON。"
)


def _classify_batch(client, batch: list[dict]) -> list[str]:
    lines = [
        f'{i}. 個股「{m["name"]}({m["ticker"]})」：{m["snippet"]}'
        for i, m in enumerate(batch)
    ]
    prompt = (
        "判斷下列每則片段對該個股的態度。\n"
        '輸出 JSON：{"results":[{"i":0,"sentiment":"bullish|bearish|neutral"}, ...]}，'
        "i 對應編號，務必涵蓋全部編號。\n\n" + "\n".join(lines)
    )
    resp = client.messages.create(
        model=SENTIMENT_MODEL,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    data = json.loads(text)
    out = ["neutral"] * len(batch)
    for r in data.get("results", []):
        i = r.get("i")
        s = r.get("sentiment", "neutral")
        if isinstance(i, int) and 0 <= i < len(batch) and s in VALID:
            out[i] = s
    return out


def classify_pending(item_date: str) -> int:
    """對指定日期、尚未判斷情緒的 mentions 分類。回傳處理筆數。"""
    if not ANTHROPIC_API_KEY:
        log.warning("未設定 ANTHROPIC_API_KEY，情緒全部標為 neutral")
        with get_conn() as conn:
            conn.execute(
                "UPDATE mentions SET sentiment='neutral' "
                "WHERE item_date=? AND sentiment IS NULL",
                (item_date,),
            )
        return 0

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, ticker, name, snippet FROM mentions "
            "WHERE item_date=? AND sentiment IS NULL",
            (item_date,),
        ).fetchall()

    pending = [dict(r) for r in rows]
    done = 0
    for start in range(0, len(pending), BATCH):
        batch = pending[start: start + BATCH]
        try:
            labels = _classify_batch(client, batch)
        except Exception as e:  # noqa: BLE001
            log.warning("情緒批次失敗，該批標 neutral：%s", e)
            labels = ["neutral"] * len(batch)
        with get_conn() as conn:
            conn.executemany(
                "UPDATE mentions SET sentiment=? WHERE id=?",
                [(labels[i], batch[i]["id"]) for i in range(len(batch))],
            )
        done += len(batch)
    return done
