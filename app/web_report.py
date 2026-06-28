"""輸出 GitHub Pages 報告頁，並自動清理超過保留期的舊報告。

  docs/index.html            最新一日報告（固定網址）
  docs/reports/<date>.html   每日封存（保留 RETENTION_DAYS 天）
  docs/.nojekyll             避免 GitHub Pages 跑 Jekyll
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import (
    ANTHROPIC_API_KEY,
    HISTORY_DIR,
    RETENTION_DAYS,
    ROOT,
    TEMPLATE_DIR,
    WEIGHT_DISCUSSION,
    WEIGHT_RECOMMENDATION,
)

log = logging.getLogger("web")

DOCS = ROOT / "docs"
REPORTS = DOCS / "reports"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _render(item_date: str, rows: list[dict], archive_dates: list[str],
            link_prefix: str, home_link: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    fields = ("rank", "name", "ticker", "total_score", "discussion_score",
              "recommendation_score", "n_sources", "n_mentions", "summary")
    slim = [{k: r.get(k) for k in fields} for r in rows]
    rows_json = json.dumps(slim, ensure_ascii=False).replace("</", "<\\/")

    tmpl = env.get_template("report.html.j2")
    return tmpl.render(
        item_date=item_date,
        rows=rows,
        rows_json=rows_json,
        archive_dates=archive_dates,
        link_prefix=link_prefix,
        home_link=home_link,
        has_ai=bool(ANTHROPIC_API_KEY),
        w_disc=WEIGHT_DISCUSSION,
        w_rec=WEIGHT_RECOMMENDATION,
    )


def _prune(folder: Path, pattern: str, cutoff: date) -> int:
    """刪除檔名日期早於 cutoff 的檔案。回傳刪除數。"""
    removed = 0
    for p in folder.glob(pattern):
        if not _DATE_RE.match(p.stem):
            continue
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d < cutoff:
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def prune_old(today: str) -> int:
    """清理超過 RETENTION_DAYS 的 docs 報告與 data/history。"""
    cutoff = date.fromisoformat(today) - timedelta(days=RETENTION_DAYS)
    removed = 0
    if REPORTS.exists():
        removed += _prune(REPORTS, "*.html", cutoff)
    if HISTORY_DIR.exists():
        removed += _prune(HISTORY_DIR, "*.json", cutoff)
        removed += _prune(HISTORY_DIR, "*.html", cutoff)
    if removed:
        log.info("清理 %d 個超過 %d 天的舊檔", removed, RETENTION_DAYS)
    return removed


def export(item_date: str, rows: list[dict]) -> str:
    """寫出 docs/ 報告頁（含清理）。回傳 index.html 路徑字串。"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    # 封存頁（同目錄連結，另含「回最新」）
    archived = _render(item_date, rows, [], link_prefix="", home_link="../index.html")
    (REPORTS / f"{item_date}.html").write_text(archived, encoding="utf-8")

    # 清理舊報告（在重建導覽前）
    prune_old(item_date)

    # 重建封存頁的歷史導覽（清理後的剩餘日期）
    dates = sorted({p.stem for p in REPORTS.glob("*.html")} | {item_date}, reverse=True)
    archived = _render(item_date, rows, dates, link_prefix="", home_link="../index.html")
    (REPORTS / f"{item_date}.html").write_text(archived, encoding="utf-8")

    # 首頁 = 最新一日；archive 連結指向 reports/ 子目錄
    latest = max(dates)
    index = _render(latest, rows, dates, link_prefix="reports/", home_link="")
    (DOCS / "index.html").write_text(index, encoding="utf-8")
    return str(DOCS / "index.html")
