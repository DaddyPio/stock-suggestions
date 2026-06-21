"""各來源抓取器。每個 collect_* 回傳 list[RawItem]，失敗時略過並記錄。"""
from __future__ import annotations

from app.collectors.base import RawItem, collect_all

__all__ = ["RawItem", "collect_all"]
