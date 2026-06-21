"""Stock-suggestions：台股輿情選股工具。

每日從新聞/評論、論壇、YouTube 字幕、Podcast shownotes 收集個股提及，
計算討論度＋推薦度綜合分，取前 N 名，用 LLM 寫 ~500 字摘要，寄 email。
"""

__version__ = "0.1.0"
