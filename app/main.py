"""進入點 CLI。

用法（py -m app.main <command>）：
  sync-universe   下載/更新股票字典
  collect         抓取各來源並抽出個股提及（不含情緒/排名）
  rank            對當日做情緒判斷 + 排名 + 摘要（不寄信）
  send            用最新排名寄信
  run             一條龍：universe→collect→sentiment→rank→summary→web→send
  web             用現有排名輸出 GitHub Pages 報告頁（docs/）
  test-email      用假資料寄一封測試信，驗證 Gmail 設定
  show            印出當日排名（不呼叫 LLM、不寄信）

共用參數：
  --date YYYY-MM-DD   指定歸屬日（預設今天台灣時間）
  --lookback N        抓「最近 N 天」內容（預設 1）
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.collectors.base import collect_all, today_tw
from app.config import TOP_N, load_sources
from app.db import get_conn, init_db


def _setup_log() -> None:
    # Windows 主控台預設 cp950，無法輸出 emoji/部分字元 → 強制 UTF-8
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_sync_universe(args) -> None:
    from app.universe import sync_universe

    n = sync_universe()
    print(f"✅ 股票字典已更新：{n} 檔")


def _load_matcher():
    from app.universe import StockMatcher, sync_universe

    sources = load_sources()
    matcher = StockMatcher(sources.get("ambiguous_names", [])).load()
    if matcher.count() == 0:
        print("字典為空，先同步股票清單…")
        sync_universe()
        matcher = StockMatcher(sources.get("ambiguous_names", [])).load()
    return matcher, sources


def cmd_collect(args) -> None:
    from app.extract import persist_and_extract

    matcher, sources = _load_matcher()
    items = collect_all(sources, lookback_days=args.lookback)
    print(f"抓到 {len(items)} 筆原始內容")
    n = persist_and_extract(items, matcher, args.date)
    print(f"✅ 新增 {n} 筆個股提及（item_date={args.date}）")


def cmd_rank(args) -> None:
    from app import ranking, sentiment, summarize

    print("① 情緒判斷…")
    sentiment.classify_pending(args.date)
    print("② 排名…")
    ranked = ranking.compute(args.date, TOP_N)
    if not ranked:
        print("⚠️ 當日無資料，無法排名")
        return
    ranking.save(args.date, ranked)
    print("③ 摘要…")
    summarize.summarize_top(args.date, ranked)
    print(f"✅ 完成前 {len(ranked)} 名排名與摘要")
    _print_ranking(args.date)


def cmd_send(args) -> None:
    from app import email_report

    rows = _fetch_ranking(args.date)
    if not rows:
        print("⚠️ 當日無排名資料，請先跑 rank")
        return
    html = email_report.render_html(args.date, rows)
    email_report.save_history(args.date, rows, html)
    ok = email_report.send(args.date, html)
    print("✅ 已寄出" if ok else "⚠️ 未寄出（設定不完整或失敗），HTML 已存 data/history")


def cmd_run(args) -> None:
    from app import email_report, ranking, sentiment, summarize
    from app.extract import persist_and_extract

    matcher, sources = _load_matcher()
    print("① 抓取…")
    items = collect_all(sources, lookback_days=args.lookback)
    n = persist_and_extract(items, matcher, args.date)
    print(f"   原始 {len(items)} 筆，新增提及 {n} 筆")
    print("② 情緒判斷…")
    sentiment.classify_pending(args.date)
    print("③ 排名…")
    ranked = ranking.compute(args.date, TOP_N)
    if not ranked:
        print("⚠️ 當日無資料，結束")
        return
    ranking.save(args.date, ranked)
    print("④ 摘要…")
    summarize.summarize_top(args.date, ranked)
    print("⑤ 輸出網頁報告…")
    from app import web_report

    rows = _fetch_ranking(args.date)
    web_report.export(args.date, rows)
    html = email_report.render_html(args.date, rows)
    email_report.save_history(args.date, rows, html)
    print("⑥ 寄信…")
    ok = email_report.send(args.date, html)
    print("✅ 完成（網頁已更新）" + ("，並已寄信" if ok else "；未寄信（無 Gmail 設定）"))


def cmd_test_email(args) -> None:
    from app import email_report

    rows = [
        {
            "rank": 1, "ticker": "2330", "name": "台積電",
            "discussion_score": 100.0, "recommendation_score": 80.0, "total_score": 92.0,
            "n_mentions": 18, "n_sources": 6, "n_bull": 12, "n_bear": 2,
            "summary": "這是一封測試信。若你能看到排版正常的卡片，代表 Gmail SMTP 設定成功。",
        }
    ]
    html = email_report.render_html(args.date, rows)
    ok = email_report.send(args.date, html)
    print("✅ 測試信已寄出" if ok else "⚠️ 寄信失敗，請檢查 GMAIL_ADDRESS / GMAIL_APP_PASSWORD")


def cmd_web(args) -> None:
    from app import web_report

    rows = _fetch_ranking(args.date)
    if not rows:
        print("⚠️ 當日無排名資料，請先跑 rank")
        return
    path = web_report.export(args.date, rows)
    print(f"✅ 網頁報告已輸出：{path}")


def cmd_show(args) -> None:
    _print_ranking(args.date)


# ---- helpers ----
def _fetch_ranking(item_date: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_rankings WHERE item_date=? ORDER BY rank",
            (item_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def _print_ranking(item_date: str) -> None:
    rows = _fetch_ranking(item_date)
    if not rows:
        print(f"（{item_date} 無排名資料）")
        return
    print(f"\n=== {item_date} 台股輿情 Top {len(rows)} ===")
    for r in rows:
        print(
            f"{r['rank']:>2}. {r['name']}({r['ticker']})  "
            f"綜合{r['total_score']}  討論{r['discussion_score']}  推薦{r['recommendation_score']}  "
            f"[{r['n_sources']}源/{r['n_mentions']}則  多{r['n_bull']}/空{r['n_bear']}]"
        )


def main() -> None:
    _setup_log()
    init_db()

    parser = argparse.ArgumentParser(prog="stock-suggestions")
    parser.add_argument("--date", default=today_tw().isoformat(), help="歸屬日 YYYY-MM-DD")
    parser.add_argument("--lookback", type=int, default=3,
                        help="抓最近 N 天內容（dedup 去重，不會重複計算；預設 3 以涵蓋週末）")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn in [
        ("sync-universe", cmd_sync_universe),
        ("collect", cmd_collect),
        ("rank", cmd_rank),
        ("send", cmd_send),
        ("run", cmd_run),
        ("web", cmd_web),
        ("test-email", cmd_test_email),
        ("show", cmd_show),
    ]:
        p = sub.add_parser(name)
        p.set_defaults(func=fn)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
