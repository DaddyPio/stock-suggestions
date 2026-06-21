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

## 已知限制

- **Podcast 無逐字稿**：多數節目只能用標題＋簡介，訊號弱；YouTube 中文自動字幕才是主力。
- **抽股雜訊**：少數公司簡稱與日常用語相同（如「大同」），已用 `ambiguous_names` 黑名單過濾，仍可能有漏網。
- **論壇穩定性**：PTT/Dcard 偶有改版或防護，屬輔助來源。

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
