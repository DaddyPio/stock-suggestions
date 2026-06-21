"""SQLite 存取層（標準函式庫 sqlite3，零外部相依）。

資料表：
  stocks         股票字典（代號↔名稱）
  raw_items      抓到的原始內容（新聞/貼文/字幕/shownotes）
  mentions       從原始內容抽出的個股提及（含情緒）
  daily_rankings 每日排名與摘要
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    market      TEXT,               -- 上市 / 上櫃
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS raw_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type  TEXT NOT NULL,     -- news / ptt / dcard / youtube / podcast
    source_name  TEXT NOT NULL,
    url          TEXT,
    title        TEXT,
    content      TEXT,
    published_at TEXT,              -- ISO 日期（盡力而為）
    fetched_at   TEXT NOT NULL,
    item_date    TEXT NOT NULL,     -- 歸屬交易日 YYYY-MM-DD
    hash         TEXT UNIQUE        -- 去重
);

CREATE TABLE IF NOT EXISTS mentions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_item_id     INTEGER NOT NULL,
    ticker          TEXT NOT NULL,
    name            TEXT,
    source_type     TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    snippet         TEXT,
    sentiment       TEXT,           -- bullish / bearish / neutral
    item_date       TEXT NOT NULL,
    FOREIGN KEY (raw_item_id) REFERENCES raw_items(id)
);

CREATE TABLE IF NOT EXISTS daily_rankings (
    item_date            TEXT NOT NULL,
    rank                 INTEGER NOT NULL,
    ticker               TEXT NOT NULL,
    name                 TEXT,
    discussion_score     REAL,
    recommendation_score REAL,
    total_score          REAL,
    n_mentions           INTEGER,
    n_sources            INTEGER,
    n_bull               INTEGER,
    n_bear               INTEGER,
    summary              TEXT,
    PRIMARY KEY (item_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_mentions_date ON mentions(item_date);
CREATE INDEX IF NOT EXISTS idx_raw_date ON raw_items(item_date);
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
