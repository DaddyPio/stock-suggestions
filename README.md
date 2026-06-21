# Stock-suggestions — 台股每日輿情選股

每天從**新聞/評論、論壇、YouTube 財經頻道、財經 Podcast** 收集個股的「討論度＋推薦度」，
取前 10 名，用 LLM 為每檔寫 ~500 字摘要，每日盤前（約 07:00 台灣時間）寄 email 給你。

> ⚠️ 僅供研究參考，非投資建議。第二階段規劃支援美股。

## 運作流程

```
① 抓取   各來源當日內容（RSS 優先；PTT/Dcard 輕量爬蟲；YouTube 中文自動字幕）
② 抽股   用 TWSE/TPEx 官方清單（~1,700 檔）字典比對 → 零成本、零幻覺
③ 情緒   Claude Haiku 判斷每則提及 看多/看空/中性
④ 排名   討論度 + 推薦度 → 綜合分 → 取前 N
⑤ 摘要   只對前 N 檔，用 Claude Sonnet 各寫 ~500 字
⑥ 寄信   Jinja2 HTML 模板 → Gmail SMTP
```

### 綜合分公式
- **討論度** = 不重複來源數 × 2 + 總提及次數（多熱）
- **推薦度** = (看多 − 看空) / 總提及次數（多看好）
- **綜合分** = 討論度(0–100) × 0.6 + 推薦度(0–100) × 0.4　← 權重可在 `.env` 調

## 安裝

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # 填入金鑰
```

`.env` 需要：
- `ANTHROPIC_API_KEY`（情緒＋摘要；與 Claude Pro 獨立計費）
- `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`（Google 帳號開兩步驟驗證後產生的「應用程式密碼」）
- `EMAIL_TO`（預設寄給自己）

## 使用

```powershell
py -m app.main sync-universe      # 第一次：下載股票字典
py -m app.main test-email         # 驗證 Gmail 設定（寄一封測試信）
py -m app.main run                # 一條龍：抓取→情緒→排名→摘要→寄信
py -m app.main run --lookback 3   # 補抓最近 3 天（剛開始資料少時好用）

# 分步執行（除錯用）
py -m app.main collect            # 只抓取＋抽股
py -m app.main rank               # 只情緒＋排名＋摘要
py -m app.main show               # 印出當日排名（不花錢、不寄信）
py -m app.main send               # 用現有排名寄信
```

不設 `ANTHROPIC_API_KEY` 也能跑：情緒全標中性、摘要留白，可先驗證抓取與排名管線。
不設 Gmail 也能跑：信件 HTML 會存到 `data/history/<date>.html`。

## 雲端排程（GitHub Actions）

`.github/workflows/daily.yml` 每交易日 22:30 UTC（= 隔天 06:30 台灣時間）自動跑 `run`，
並把當日結果 commit 到 `data/history/`。需在 repo 設定這些 **Secrets**：

| Secret | 說明 |
|---|---|
| `ANTHROPIC_API_KEY` | LLM |
| `GMAIL_ADDRESS` | 寄件 Gmail |
| `GMAIL_APP_PASSWORD` | Gmail 應用程式密碼 |
| `EMAIL_TO` | 收件者（逗號分隔） |

手動觸發：GitHub → Actions → Daily Stock Buzz → Run workflow。

## 來源設定

全部來源列在 [`config/sources.yml`](config/sources.yml)，可自由增刪：
新聞 RSS、PTT/Dcard、YouTube 頻道（填 `@handle` 或 `channel_id`）、Podcast RSS。
**任一來源失敗都會被略過，不影響整體。**

> RSS 網址與 YouTube handle 可能隨網站改版失效，這是目前最脆弱的環節，發現抓不到時優先檢查這裡。

## Podcast 語音轉錄（股癌等純音檔節目）

部分節目（如**股癌**）YouTube 字幕關閉、shownotes 又多為業配，抽不到內容。
對這類節目在 `config/sources.yml` 標記 `transcribe: true`，會用 **faster-whisper**
（CPU、免費）下載音檔轉逐字稿：

```yaml
podcast_rss:
  - name: 股癌 Gooaye
    url: https://feeds.soundon.fm/podcasts/954689a5-...xml
    transcribe: true
whisper:
  model: base                 # base 最快；small 較準但慢
  language: zh
  max_episodes_per_feed: 1    # 每次最多轉幾集（控時間）
```

- 逐字稿快取在 `data/cache/transcripts/`，同一集不重複轉錄。
- 本機 base 模型轉一集 ~30-40 分鐘音檔約需 **8-9 分鐘**；Actions 已設 45 分鐘 timeout 並快取模型。
- **準確度取捨**：base 模型會聽錯字（如「股癌」→「古癌」、輝達常漏抓），個股漏抓/誤判會增加；要更準可改 `model: small`（較慢）。

## 已知限制

- **抽股雜訊（中文無詞界）**：2 字公司簡稱可能命中日常用語的子字串（如「和大」命中「和大聲」、「世界」命中「世界盃」）。已用兩道防線降噪：
  1. `ambiguous_names` 黑名單（常用詞簡稱改用代號命中）
  2. 年份/代號衝突過濾（如「2024」年份不會誤判成志聯，除非名稱也出現）

  殘留的單來源、低頻雜訊因排名以「不重複來源數」加權，幾乎不會進前 10。徹底解法是 jieba 中文斷詞（後續優化）。
- **論壇穩定性**：PTT 可用；Dcard 偶有 Cloudflare 403，屬輔助來源。
- **來源失效**：RSS 網址 / YouTube channel_id 可能隨改版失效，抓不到時優先檢查 `config/sources.yml`。

## 專案結構

```
app/
  main.py            # CLI 進入點
  config.py          # 環境變數 + 來源設定
  db.py              # SQLite schema
  universe.py        # 股票字典 + 抽股 matcher
  collectors/        # news_rss / ptt / dcard / youtube / podcast
  extract.py         # 入庫 + 抽提及
  sentiment.py       # LLM 情緒判斷（Haiku）
  ranking.py         # 討論度+推薦度綜合分
  summarize.py       # LLM 摘要（Sonnet）
  email_report.py    # HTML + Gmail SMTP
config/sources.yml   # 來源清單
templates/email.html.j2
data/                # SQLite（ephemeral）+ history JSON/HTML
```
