# Strategy Research Report — Validation & New Candidates

This document summarizes a deep literature review (academic papers, practitioner
research, and industry sources, 2012–2026) used to (1) validate the 11 strategies
already implemented in this project and (2) identify new strategies worth adding.

**Bottom line up front:** No strategy guarantees profit. The evidence strongly
favors **slow trend-following / time-series momentum** (the most robust anomaly in
finance, validated across two centuries and dozens of markets), with **volatility
scaling** as the single most important risk improvement. Short-term / intraday
trend-following has measurably degraded since ~2009. Mean-reversion (RSI/Bollinger)
only works in range-bound regimes and loses in trends. The "modern edge" cited
across recent literature is **regime awareness** — switching between trend and
mean-reversion depending on market state.

---

## 1. Validation of the 11 existing strategies

| # | Strategy | Verdict | Evidence |
|---|----------|---------|----------|
| 1 | Time-series momentum (12m) | ✅ **Strongest, keep** | Moskowitz–Ooi–Pedersen (2012); AQR "Century of Evidence" (1880–2013). Works across all asset classes. Highest raw return in our rankings. |
| 2 | Donchian breakout (Turtle) | ✅ **Keep** | Curtis Faith *Way of the Turtle*. Best risk-adjusted in our backtests (Sortino ~1.08). Same trend-following family as #1. |
| 3 | Trend following (vol-aware) | ✅ **Keep** | Same family as #1/#2. Regime filter (price > 200-SMA) is well-supported. |
| 4 | Moving-average crossover | ✅ **Keep (basic)** | Brock–Lakonishok–LeBaron (1992), Dow 1897–1986. Works but whipsaws in ranges. |
| 5 | MACD | ⚠️ **Keep (minor)** | Trend-following variant; adds little over MA crossover. |
| 6 | Volatility breakout (Keltner) | ⚠️ **Keep (minor)** | Trend-following variant with RSI confirmation. |
| 7 | Intraday momentum (EMA) | ✅ **Keep (day-trading)** | The only day-trading strategy with a real edge in our tests (profit factor ~4.9–5.7 on QQQ/TQQQ). Consistent with intraday-momentum literature (Gao et al. 2018; Li et al. 2022). |
| 8 | Opening range breakout (ORB) | ✅ **Keep (day-trading)** | Holmberg–Lönnbark–Lundström (2013); **Zarattini & Aziz (2025)** — ORB on QQQ earned ~33% annualized alpha net of fees (2016–2023); 1,484% on TQQQ vs 169% buy-and-hold QQQ. Low win rate (~24%) compensated by asymmetry. |
| 9 | RSI | ❌ **Weak — demote** | Sortino ≈ 0 in our rankings. Mean-reversion on RSI alone is not a standalone edge. |
| 10 | Bollinger bands | ⚠️ **Regime-dependent** | Works only in range-bound regimes; loses in trends. Keep only as a regime component. |
| 11 | Z-score mean reversion | ⚠️ **Regime-dependent** | Same as #10. Useful inside a regime-switching wrapper, not standalone. |

### Key validation findings (with sources)

1. **Trend following is the most robust anomaly ever documented.** It has been
   profitable for at least two centuries across virtually every liquid market
   (Lempérière et al. 2014; Hurst, Ooi & Pedersen 2017; Moskowitz, Ooi & Pedersen
   2012). AQR's "A Century of Evidence on Trend-Following Investing" (1880–2013)
   confirms it across asset classes.

2. **But short-term trend-following has degraded since ~2009.** Kurth, Eisler, Rej
   & Bouchaud (2026), *"Is Trend Still Your Friend?"* (arXiv:2607.01550) document a
   break: fast (days-to-weeks) trend signals collapsed post-2008, while slow trends
   (months) largely survived. The cross-sectional driver is the
   volatility-normalized tick size — small-tick contracts degraded, large-tick ones
   did not. **Implication: prefer slow horizons (12-month) over fast intraday
   trend signals.**

3. **Trend following on individual stocks is highly skewed.** Zarattini, Pagani &
   Wilcox (2025), *"Does Trend-Following Still Work on Stocks?"* (1950–2024,
   66,000+ trades): **<7% of trades drive all the profit**. Net-of-fee viability is
   poor for small accounts (<$1M AUM) due to turnover costs, unless a
   turnover-control / volatility filter is applied. **Implication: our ATR-based
   sizing + low turnover + ETF universe (not single stocks) is the right design.**

4. **Day trading is hard — most retail day traders lose.** Harris & Schultz
   (*Financial Analysts Journal*, 2003): ~2× as many day traders lose as win; only
   ~1 in 5 is more than marginally profitable. **Implication: day-trading mode
   should be treated as experimental; the swing/trend mode is the safer default.**

5. **ORB has genuine academic support** (contrary to common retail folklore).
   Zarattini & Aziz (2025) show ORB on QQQ/TQQQ can produce significant net alpha,
   but it requires leverage (or leveraged ETFs) and disciplined stops. Our
   implementation (long-only, ATR stops) is a conservative version of this.

---

## 2. New strategies identified (ranked by evidence strength)

### Tier 1 — Strongest evidence, worth implementing

**A. Volatility-scaled momentum (Barroso & Santa-Clara 2015).**
Momentum has occasional violent crashes ("momentum crashes", Daniel & Moskowitz
2016). Scaling position size inversely to realized volatility (constant-volatility
scaling, CVS) removes most of the crash risk and is the single best risk-adjusted
improvement in the literature. Kim et al. (2018) find CVS momentum the most
efficient (15.3% annual return across 55 futures). **Implemented here as
`volatility_scaled_momentum`.**

**B. Regime-adaptive / regime-switching strategy.**
The recurring "modern edge" across 2024–2026 literature: momentum and mean-reversion
are *regime-dependent*, not always-on. A meta-layer that detects the regime (trend
vs. range, e.g. via trend strength / ADX / VIX) and applies the matching strategy
avoids the whipsaw losses that kill single-strategy systems. Supported by
QuantInsti (HMM regime detection), Springer *Digital Finance* (2025), and multiple
practitioner sources. **Implemented here as `regime_adaptive`.**

### Tier 2 — Strong but harder to implement in this architecture

**C. Pairs trading / statistical arbitrage.**
The most-cited "new" strategy class. Stübinger & Bredthauer (2017) report Sharpe
~8 on high-frequency pairs (S&P 500, 1998–2015), though most pairs approaches show
declining returns over time (crowding). ML-enhanced versions (graph clustering,
Korniejczuk & Ślepaczuk 2024) improve signal quality. **Requires two correlated
symbols + shorting — noted as future work (our broker is long-only).**

**D. Overnight vs. intraday anomaly ("Night Moves").**
Elm Wealth (2026) and Bogousslavsky (2021) document that a large share of equity
returns accrues *overnight*, and a long-short overnight strategy has a Sharpe
~10× that of long-short momentum. Cross-market overnight momentum (Xu 2025) is
significant out-of-sample. **Requires shorting + precise session timing — future
work.**

**E. Cross-sectional momentum (12-1).**
Jegadeesh & Titman (1993); ~15.19% CAGR long-only (Zarattini 2025). Requires a
ranked universe of many stocks (not our 5-ETF universe) — future work.

### Tier 3 — Documented but high-complexity / high-risk

**F. Volatility risk premium / systematic options selling.**
Selling 30–45 DTE options / put spreads harvests the vol risk premium (~10–18%
annual with discipline), but carries tail risk (20–40% drawdowns in bear markets)
and needs options permissions. **Not implemented — outside current scope.**

**G. ML / RL (deep Q-learning, gradient boosting, LSTM).**
Prominent in 2024–2026 literature but flagged repeatedly for overfitting risk and
backtest-to-live decay of 50–80%. **Not implemented — kept as a research direction.**

---

## 3. What this means for the current system

- **Default (swing) mode** should lean on slow trend-following / time-series
  momentum with volatility scaling — the most defensible, lowest-turnover edge.
- **Day-trading mode** (current default) is the riskiest; keep it but treat
  intraday momentum + ORB as the only day-trading strategies with evidence.
- **RSI** should be demoted from any standalone role.
- **Volatility scaling** and **regime awareness** are the two highest-value
  upgrades, and both are now implemented (see `strategy.py`).

---

## 4. Sources

- Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*, JFE.
- Hurst, Ooi & Pedersen (2017), *A Century of Evidence on Trend-Following Investing*, JPM.
- Kurth, Eisler, Rej & Bouchaud (2026), *Is Trend Still Your Friend?*, arXiv:2607.01550.
- Zarattini, Pagani & Wilcox (2025), *Does Trend-Following Still Work on Stocks?*, SSRN 5084316.
- Zarattini & Aziz (2025), *Can Day Trading Really Be Profitable?* (ORB on QQQ/TQQQ).
- Holmberg, Lönnbark & Lundström (2013), *Assessing the profitability of intraday ORB*, Finance Research Letters.
- Harris & Schultz (2003), *The Profitability of Day Traders*, Financial Analysts Journal.
- Barroso & Santa-Clara (2015), *Momentum has its moments*, JFE.
- Daniel & Moskowitz (2016), *Momentum Crashes*, JFE.
- Kim et al. (2018), *Risk-adjusted momentum strategies*, Int. Rev. Financial Analysis.
- Jegadeesh & Titman (1993), *Returns to Buying Winners and Selling Losers*, JF.
- Stübinger & Bredthauer (2017), *Statistical arbitrage pairs trading with high-frequency data*.
- Korniejczuk & Ślepaczuk (2024), *Statistical arbitrage via graph clustering*, arXiv:2406.10695.
- Bogousslavsky (2021), *The cross-section of intraday and overnight returns*, JFE.
- Elm Wealth (2026), *Night Moves: Overnight Drift*.
- Xu et al. (2025), *Cross-market overnight time-series momentum*, JIFMIM.
- Brock, Lakonishok & LeBaron (1992), *Simple Technical Trading Rules*, JF.
- Curtis Faith, *Way of the Turtle*; Gary Antonacci, *Dual Momentum Investing*.
