"""產生 HTML 信件並透過 Gmail SMTP 寄出。"""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import (
    EMAIL_TO,
    GMAIL_ADDRESS,
    GMAIL_APP_PASSWORD,
    HISTORY_DIR,
    TEMPLATE_DIR,
    WEIGHT_DISCUSSION,
    WEIGHT_RECOMMENDATION,
)

log = logging.getLogger("email")


def render_html(item_date: str, rows: list[dict]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    tmpl = env.get_template("email.html.j2")
    return tmpl.render(
        item_date=item_date,
        rows=rows,
        w_disc=WEIGHT_DISCUSSION,
        w_rec=WEIGHT_RECOMMENDATION,
    )


def save_history(item_date: str, rows: list[dict], html: str) -> None:
    """把當日結果存成 JSON＋HTML（可 commit 進 repo 留歷史）。"""
    (HISTORY_DIR / f"{item_date}.json").write_text(
        json.dumps({"item_date": item_date, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (HISTORY_DIR / f"{item_date}.html").write_text(html, encoding="utf-8")


def send(item_date: str, html: str) -> bool:
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and EMAIL_TO):
        log.warning("Gmail 設定不完整，跳過寄信（HTML 已存於 data/history）")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 台股每日輿情 Top 榜 — {item_date}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = ", ".join(EMAIL_TO)
    msg.attach(MIMEText("請以支援 HTML 的信件軟體開啟。", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, EMAIL_TO, msg.as_string())
        log.info("已寄信給 %s", ", ".join(EMAIL_TO))
        return True
    except Exception as e:  # noqa: BLE001
        log.error("寄信失敗：%s", e)
        return False
