"""集中管理環境變數與來源設定。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = ROOT / "config"
TEMPLATE_DIR = ROOT / "templates"

DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "buzz.db"
HISTORY_DIR = DATA_DIR / "history"
HISTORY_DIR.mkdir(exist_ok=True)

# ---- LLM ----
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SENTIMENT_MODEL = os.getenv("SENTIMENT_MODEL", "claude-haiku-4-5-20251001")
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "claude-sonnet-4-6")

# ---- Email ----
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
EMAIL_TO = [e.strip() for e in os.getenv("EMAIL_TO", GMAIL_ADDRESS).split(",") if e.strip()]

# ---- Ranking ----
TOP_N = int(os.getenv("TOP_N", "10"))
WEIGHT_DISCUSSION = float(os.getenv("WEIGHT_DISCUSSION", "0.6"))
WEIGHT_RECOMMENDATION = float(os.getenv("WEIGHT_RECOMMENDATION", "0.4"))

# 歷史報告保留天數（超過即自動清理）
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "60"))

# 通用 HTTP header，降低被擋機率
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def load_sources() -> dict:
    """讀取 config/sources.yml。"""
    with open(CONFIG_DIR / "sources.yml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
