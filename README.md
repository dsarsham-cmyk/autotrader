# Auto Trader

A complete, production-grade algorithmic trading system in Python. It connects
to a real brokerage API, automatically executes a volatility-aware
trend-following strategy, and manages risk end-to-end.

## What it does

- 🔌 **Connects to a real broker** — Alpaca (stocks, paper + live), ccxt (crypto), yfinance (data)
- 🌍 **Multi-market** — trades a portfolio of symbols across regions (US, Japan, Eurozone, UK, …) via ETFs
- 📈 **Executes a strategy automatically** — 11 strategies (trend following, breakout, mean reversion, momentum, day trading) with ATR-based position sizing, stop-loss, and take-profit
- 🌙 **Day-trading mode** — opens intraday positions and closes them before market close (no overnight risk)
- 🕐 **Market-hours awareness** — only trades when the market is open (Alpaca clock)
- 🛡️ **Server-side stops** — bracket orders (stop-loss + take-profit) enforced by the broker, surviving bot restarts
- 🛡️ **Risk management** — risk-per-trade sizing, daily loss limit, max-drawdown kill switch
- 🧪 **Backtesting + walk-forward optimization** — validates strategies out-of-sample to avoid overfitting
- 🖥️ **Web dashboard** — live balance, positions, trades, equity chart
- 🔔 **Trade alerts** — Telegram / Discord
- 💾 **State persistence** — resumes after restart

## Quick start

### 1. Create a free Alpaca paper account (2 minutes)

1. Go to https://alpaca.markets and sign up with your email.
2. Verify your email (click the link in your inbox).
3. In the dashboard, switch to **Paper Trading**.
4. Generate API keys (Overview → API Keys).
5. Copy them into `.env` (see below).

> Paper trading is **free**, requires **no identity verification/KYC**, and
> works globally. It simulates real fills against live market data.

### 2. Configure

```bash
cd autotrader
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# Copy .env.example to .env and add your Alpaca paper keys:
#   ALPACA_API_KEY=...
#   ALPACA_API_SECRET=...
```

### 3. Run

```bash
python backtest.py --limit 1000     # backtest the strategy (no keys needed)
python walkforward.py --limit 2000  # walk-forward validation
python compare.py --symbols AAPL MSFT SPY  # rank all strategies
python bot.py                       # paper trade (simulated)
python dashboard.py                 # live dashboard at http://127.0.0.1:8050
```

## The strategy

**Default (swing):** volatility-scaled momentum — 12-month time-series
momentum on daily bars, with a volatility filter that avoids entering during
momentum crashes. This is the most defensible strategy per the research
(see [RESEARCH.md](RESEARCH.md)); it holds positions overnight rather than
day-trading.

**All available strategies** (`strategy.name` in `config.yaml`):

| Strategy | Type | Notes |
|----------|------|-------|
| `intraday_momentum` | Day trading | EMA crossover on intraday bars |
| `opening_range_breakout` | Day trading | Break of the first bars' range |
| `donchian_breakout` | Breakout | Turtle-style 20-day high / 10-day low |
| `trend_following` | Trend | Regime filter + EMA crossover |
| `moving_average_crossover` | Trend | Golden/death cross |
| `volatility_breakout` | Breakout | Keltner channel + RSI confirmation |
| `time_series_momentum` | Momentum | 12-month momentum (Moskowitz et al.) |
| `zscore_mean_reversion` | Mean reversion | Z-score entry/exit |
| `bollinger_bands` | Mean reversion | Band reversion |
| `rsi` | Mean reversion | Overbought/oversold |
| `macd` | Trend | MACD crossover |
| `volatility_scaled_momentum` | Momentum | TSMOM with a volatility filter (Barroso & Santa-Clara) |
| `regime_adaptive` | Adaptive | Switches trend-following vs mean-reversion by regime |
| `vwap_mean_reversion` | Day trading | Mean-reversion around VWAP |
| `gap_and_go` | Day trading | Trade the opening gap direction |
| `volume_breakout` | Day trading | Breakout with volume confirmation |

See [RESEARCH.md](RESEARCH.md) for the full literature review that validates
these strategies and ranks new candidates.

**Shared risk/execution model** (all strategies):

1. **Position sizing** — risk a fixed fraction of equity per trade, sized by ATR (smaller positions in volatile markets).
2. **Stop-loss / take-profit** — 2×ATR stop, 3×ATR take (server-side bracket orders on Alpaca).
3. **Day trading** — when `day_trading.close_at_eod` is true, positions are closed before market close.

All parameters are configurable in `config.yaml`.

## Pairs trading (statistical arbitrage)

A long-short mean-reversion strategy on the log price ratio of two correlated
ETFs (e.g. QQQ vs SPY). When one leg becomes expensive relative to the other
(|z| > `entry_z`), it shorts the expensive leg and longs the cheap leg, betting
on convergence.

```bash
python pairs.py --backtest   # backtest the configured pair
python pairs.py              # live paper-trade the pair (Alpaca, supports shorting)
```

Configured under the `pairs:` section in `config.yaml`. This is the strategy
class most cited in recent research (statistical arbitrage), but it requires
shorting, so it is kept separate from the long-only single-symbol bot.

> ⚠️ **Honest note on profitability:** no strategy guarantees profit. Backtesting
> showed Donchian breakout has the best risk-adjusted returns (Sortino ~1.1) and
> time-series momentum the highest raw return, but day-trading strategies earn
> small absolute returns. The system is built to manage risk and avoid
> catastrophic losses, not to promise returns.

## Configuration

Everything is in [config.yaml](config.yaml):

| Key | Description |
|-----|-------------|
| `mode` | `paper` (simulated), `alpaca_paper` (Alpaca demo), or `live` |
| `market` | `stock`, `crypto`, or `forex` |
| `stock.symbols` | list of tickers to trade (one position per symbol) |
| `strategy.name` | any strategy from the table above |
| `risk.risk_per_trade` | fraction of equity risked per trade |
| `risk.atr_stop_mult` | stop-loss distance in ATRs |
| `risk.atr_take_mult` | take-profit distance in ATRs |
| `risk.max_position_pct` | max single position size |
| `risk.daily_loss_limit_pct` | stop trading for the day after this loss |
| `risk.max_drawdown_pct` | hard kill switch |
| `day_trading.close_at_eod` | close all positions before market close |
| `day_trading.eod_close_time` | local time (HH:MM) to close positions |

## Going live

1. Complete identity verification on Alpaca (required only for live trading).
2. Generate **live** API keys and put them in `.env`.
3. Set `mode: live` in `config.yaml`.

> ⚠️ **Live trading risks real money.** Paper-trade and backtest thoroughly
> first. No strategy guarantees profit — the system is built to manage risk
> and avoid catastrophic losses, not to promise returns.

## Project layout

| File | Purpose |
|------|---------|
| `bot.py` | Main trading loop (strategy + risk + execution) |
| `strategy.py` | 16 strategies + `PairsTrading` (trend, momentum, mean reversion, adaptive, day trading) |
| `pairs.py` | Pairs trading runner (backtest + live long-short) |
| `RESEARCH.md` | Literature review: strategy validation + new candidates |
| `risk.py` | Position sizing, stops, portfolio limits |
| `broker.py` | Paper + live brokers (Alpaca, ccxt) |
| `price_feed.py` | Market data (yfinance, ccxt) |
| `backtest.py` | Backtesting engine with ATR sizing + intra-bar stops |
| `walkforward.py` | Walk-forward optimization (anti-overfitting) |
| `compare.py` | Rank strategies/tickers |
| `dashboard.py` | Flask web dashboard |
| `state.py` | JSON state persistence |
| `alerts.py` | Telegram/Discord notifications |
| `logger.py` | Logging setup |
| `tests/` | Unit tests |

## Tests

```bash
python -m pytest tests/
```
