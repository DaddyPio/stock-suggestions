"""輸出 GitHub Pages 報告頁。

  docs/index.html            最新一日報告（固定網址）
  docs/reports/<date>.html   每日封存
  docs/.nojekyll             避免 GitHub Pages 跑 Jekyll
"""
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import (
    ANTHROPIC_API_KEY,
    ROOT,
    TEMPLATE_DIR,
    WEIGHT_DISCUSSION,
    WEIGHT_RECOMMENDATION,
)

DOCS = ROOT / "docs"
REPORTS = DOCS / "reports"


def _render(item_date: str, rows: list[dict], archive_dates: list[str],
            link_prefix: str, home_link: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    tmpl = env.get_template("report.html.j2")
    return tmpl.render(
        item_date=item_date,
        rows=rows,
        archive_dates=archive_dates,
        link_prefix=link_prefix,
        home_link=home_link,
        has_ai=bool(ANTHROPIC_API_KEY),
        w_disc=WEIGHT_DISCUSSION,
        w_rec=WEIGHT_RECOMMENDATION,
    )


def export(item_date: str, rows: list[dict]) -> str:
    """寫出 docs/ 報告頁，回傳 index.html 路徑字串。"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    # 蒐集所有封存日期（含本次），新到舊
    dates = sorted(
        {p.stem for p in REPORTS.glob("*.html")} | {item_date}, reverse=True
    )

    # 封存頁：同目錄連結，另含「回最新」
    archived = _render(item_date, rows, dates, link_prefix="", home_link="../index.html")
    (REPORTS / f"{item_date}.html").write_text(archived, encoding="utf-8")

    # 首頁 = 最新一日；archive 連結指向 reports/ 子目錄
    latest = max(dates)
    index_rows = rows  # 本次執行即最新日（每日排程情境）
    index = _render(latest, index_rows, dates, link_prefix="reports/", home_link="")
    (DOCS / "index.html").write_text(index, encoding="utf-8")
    return str(DOCS / "index.html")
