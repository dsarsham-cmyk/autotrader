# Auto Trader — Project Handoff (for ChatGPT / next AI)

> Paste this entire document into ChatGPT to continue the project. It contains
> the project location, current state, credentials, and open tasks.

---

## 1. What this project is

An **automated stock-trading bot** (paper/demo trading, no real money) that runs
24/7 in the cloud and trades two strategies side by side on the same Alpaca
paper account:

- **HIGH RISK** — 3 leveraged ETFs (TQQQ, SPXL, SOXL), aims for higher return.
- **LOW RISK** — 8 diversified ETFs (US + Japan + Europe: QQQ, SPY, DIA, IWM,
  EWJ, EZU, EWU, EWG), steadier and lower drawdown.

Strategy used by both: `volatility_scaled_momentum` (time-series momentum with a
volatility filter) on **daily bars**.

---

## 2. Where the code lives

- **GitHub (primary, ChatGPT can clone/browse this):**
  `https://github.com/dsarsham-cmyk/autotrader` — branch `main`
- **Local Windows path (this machine):**
  `C:\Users\Ars7am\.lmstudio\apps\bionic\projects\d49037d8-47f4-5808-9028-c707de117f8f\workspace\autotrader`
  (Python venv at `.venv\Scripts\python.exe`, shell is **bash**)

---

## 3. Current state (as of 2026-09-17)

- ✅ Bot is **live and healthy** on **Railway** (cloud, 24/7). Service name
  `autotrader`, project ID `b3c07860-2efa-471e-bb23-1dce2f5a827e`.
  - Deploy: `railway up -d --service autotrader` (run from the `autotrader/` dir)
  - Logs: `railway logs --service autotrader`
- ✅ Over-leverage bug **fixed** (each scenario now capped at 50% of the
  account, total ≤100%, no more negative cash / margin).
- ✅ Account cleaned: equity ≈ **$101.8k**, 11 positions (3 high + 8 low),
  positive cash, no errors.
- ✅ Web dashboard live: `https://dsarsham-cmyk.github.io/autotrader/`
- ✅ Windows desktop app built: `AutoTrader.exe` on the Desktop.
- ✅ Telegram alerts: every trade, status every 15 min while market open, daily
  report after US close.

---

## 4. Architecture (key files, all under `autotrader/`)

| File | Purpose |
|---|---|
| `bot.py` | Main loop: fetch data → evaluate strategy → size positions → place orders → manage stops |
| `run_all.py` | Supervisor: runs BOTH scenarios (config_high + config_low), restarts on crash, sends daily report |
| `strategy.py` | All strategies (`volatility_scaled_momentum`, etc.) |
| `risk.py` | Position sizing (ATR-based), stops, `capital_fraction`, portfolio limits |
| `broker.py` | Alpaca broker (paper), position/order handling |
| `config_high.yaml` / `config_low.yaml` | Scenario configs (symbols, risk, capital_fraction) |
| `snapshot.py` | Read-only: reads Alpaca → writes `dashboard.json` (run by GitHub Actions every 30 min) |
| `scenario_backtest.py` | Portfolio-level backtest harness (6-yr historical validation) |
| `backtest_results.json` | Committed backtest results (shown in dashboard) |
| `report.py` | Daily Telegram report |
| `alerts.py` | Telegram/Discord/ntfy alert sending |
| `index.html` | The dashboard (GitHub Pages) |
| `desktop_app.py` + `build_windows.bat` | Windows desktop app (pywebview) + build script |
| `.env` | Secrets (gitignored, NOT on GitHub) |

---

## 5. Credentials (paper/demo — NOT real money)

These are in `.env` (gitignored). ChatGPT will need them to run the bot locally:

```
ALPACA_API_KEY=PKSNWVS6B5PRSF5XGIPSYT3UVW
ALPACA_API_SECRET=9DFLhFK75Fkga1HFUuyGwiTneUEaac1gjMzpNQexVzS7
TELEGRAM_BOT_TOKEN=8655607295:AAEywXHfTkLyxUUrifoOv_okEnrXADaGxDE
TELEGRAM_CHAT_ID=5420339107,-5350554684
```

- Alpaca paper endpoint: `https://paper-api.alpaca.markets`
- These are **Alpaca paper-trading keys** (demo account, $100k starting balance).

---

## 6. Honest backtest results (6 years, daily bars)

| Scenario | Total return | Annualized | Max drawdown | Win rate |
|---|---|---|---|---|
| HIGH risk | +22.9% | +3.4%/yr | 33.8% | 35.4% |
| LOW risk | +4.0% | +0.6%/yr | 5.4% | 39.5% |

**Important reality check:** the user repeatedly asks for 1–2% *daily* profit.
That is not achievable (~500%+ annualized). The honest, deployable result is a
modest positive return with controlled risk. Do NOT over-promise; the user
values honesty but gets frustrated by "weak" strategies.

---

## 7. User context & preferences (important)

- **Non-technical.** Wants action and results, not long explanations. Gets
  frustrated by repeated caveats, but also explicitly asked for honesty.
- **Wants daily profit and frequent trading**, but research already proved only
  slow daily swing momentum is profitable (intraday/day-trading loses money).
- **Wants 24/7 cloud** (Railway), NOT on their PC. Two scenarios monitored
  side by side.
- **Wants a dashboard** to see everything (equity, positions, P&L, backtest,
  recent trades, errors) — already built.
- **Wants Telegram alerts** — already working.
- Email `ds.arsham@gmail.com` · GitHub `dsarsham-cmyk` · timezone
  Europe/Bucharest · Windows 11, bash shell.
- Has authorized: use their Chrome, create accounts, deploy end-to-end, use
  their GitHub/Railway/Alpaca/Telegram.

---

## 8. Open tasks / ideas for next steps

1. **Exit-plan tuning** — the user wants positions held overnight when losing
   (already done) but the trailing-stop / take-profit could be optimized.
2. **More frequent signals** — user wants more than ~1 trade/day; consider a
   shorter lookback or additional symbols, but validate via `scenario_backtest.py`
   first (never deploy an unvalidated change).
3. **Two separate paper accounts** — currently both scenarios share one account
   (split 50/50 via `capital_fraction`). Could use a 2nd Alpaca paper account
   for cleaner separation.
4. **Telegram command bot** — add `/status`, `/positions`, `/pause` commands so
   the user can control the bot from their phone.
5. **Improve the prediction engine** — the user believes the strategy is "too
   weak" and wants a stronger edge. Any new strategy MUST be validated
   out-of-sample before deploying.

---

## 9. How to run locally (for testing)

```bash
cd autotrader
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scenario_backtest.py --years 6   # backtest both scenarios
.venv/Scripts/python.exe snapshot.py                      # refresh dashboard.json
.venv/Scripts/python.exe report.py --dry-run              # preview daily report
```

Deploy to cloud: `railway up -d --service autotrader`
