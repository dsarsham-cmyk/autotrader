# Paper safety policy — 2026-09-26

This policy applies only to the existing Alpaca PAPER account. It does not
enable or certify real-money trading. Daily momentum signals remain unchanged;
execution and holding-period rules have changed. The old six-year backtest
does not establish profitability under this new policy.

## Account-wide rules

- At 0.5% below broker previous-close equity: cancel pending buys and block new
  purchases for the rest of the New York date, even if equity recovers.
- At 1% below previous close: request liquidation of ALL holdings and cancel
  outstanding entries. Keep checking until positions and active orders are gone.
  No same-day re-entry.
- Five minutes before the broker clock's next close, including early closes:
  request liquidation of ALL holdings, including losers. Overnight carryover
  triggers continued liquidation next session.
- HIGH allocation: 25% of account equity; LOW: 50%. Whole-share entry quantities,
  cash-based sizing, no intentional borrowing. Leveraged ETFs still amplify risk.
- An entry is a DAY limit bracket with both take-profit and stop-market legs
  present in the original request. No fractional/notional bracket entries.
- Existing positions require verified active sell-stop quantity covering the
  complete holding. Held/inactive, undersized and stop-limit orders do not qualify.
  Missing protection blocks new exposure and triggers account liquidation.
  Partially filled bracket entries whose stops have not activated are canceled
  and exited; there is no grace period that labels them protected.
- Existing break-even/trailing rules remain software exits using fresh quotes;
  a static broker stop remains in force until an exit is requested.
- At most one entry attempt per symbol per NY date. All orders have deterministic
  client IDs. Uncertain responses are reconciled before duplicate submission.
- Pending exit orders are not duplicated. Conflicting orders must disappear from
  broker inventory before a market exit is submitted. Rejected/canceled exits
  use a 60-second cooldown and a new ID only after terminal status is confirmed.
- Existing 10% starting-equity and peak-drawdown guards remain permanent halts.
  On initial installation, the peak is seeded from available one-month daily
  broker history; earlier/unobserved intraday highs cannot be reconstructed.

## Cloud operation and evidence

`run_all.py` supervises exactly one `safe_paper_engine.py` order writer; both
portfolios share its risk decisions. The strategy data collector and notification
worker are separate threads. Historical data/Telegram delays do not block the
safety loop. Risk polling targets ten seconds; API delays can make it longer.
Snapshot publication is separate and never places orders.

Safety state is written atomically to the Railway volume at
`/data/safety_state.json`. Pending exits, loss halts, attempted symbols and
observed peaks survive process restarts and deployments. Missing/corrupt state
blocks entries that date and queues inherited holdings for liquidation.
The application does not silently treat a state loss as permission to trade.

`/health` and `/dashboard.json` expose a public paper-only `safety` object:
freshness, triggers, verified stops, actual open-position count, pending actions
and errors. Process uptime is NOT evidence of successful order execution.
The UI rejects safety status older than 45 seconds. Notifications distinguish
requested/pending exits from confirmed flat inventory.

## Limits and testing

These are trigger levels, NOT guaranteed maximum losses. Markets can gap;
orders can be rejected, fill partially or slip; outages can delay action.
Bracket stops only activate after the parent fully fills. Market exits queued
while the exchange is closed cannot execute until an eligible session.
Whole-share brackets may make this policy unsuitable for very small accounts.

Run `python -m pytest -q`. New tests cover boundary thresholds, session latches,
restart recovery, early closes, losing-position exits, cancel confirmation,
partial fills, idempotency, rejected-exit retries, coverage, sizing, stale quotes,
stale clocks, trailing exits and live-endpoint refusal. These are simulated tests,
not proof of real exchange execution. Confirm the first market session's actual
fills and protection before drawing conclusions about readiness or profitability.
