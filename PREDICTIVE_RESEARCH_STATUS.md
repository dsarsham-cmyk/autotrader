# Predictive research — 2026-10-10

Objective remains unmet: at least 90% profitable ACTIVE days, net profit after
costs, unchanged budgets/loss limits, and independent forward evidence.
No-trade days are not wins. No model here is authorized to submit broker orders.

## New exploratory experiments

`predictive_portfolio_research.py` compares logistic and boosted classifiers on
20 fixed present-day stocks, two decision times and four exit rules. Historical
results are in ignored `research_runs/predictive_portfolio/results.json` and
`research_runs/predictive_portfolio_conditioned/results.json`. The latter fits
and calibrates only on simulated filled historical orders; prediction and
selection do not prefilter future test candidates by their eventual fills.
No variant passed the research target screen. Tiny samples with apparent 100%
success do not qualify. These dates were previously explored, not untouched.

`quantum_kernel_research.py` compares an RBF kernel and a four-qubit simulated
fidelity kernel using identical training-only scaler/PCA, fixed C=1, fixed
thresholds, expanding training, 60 calibration dates and 20-date test blocks.
Each fit uses a deterministic maximum of 600 past training and calibration
rows. Two encoding layers use H, RZ and ring CZ gates. This is a CPU statevector
simulation, not quantum hardware, computational advantage, or market physics.

Data: cached SIP minute bars, 20 stocks, 176 exploratory test sessions, 9 folds.
All scenarios use the existing research portfolio simulator: cash-only, at
most three positions, 1% account per stock, 5% category cap, 1% price stops,
conservative gap handling, whole shares, signal-frozen entry limits, and no
overnight exposure. Primary cost is 10 bps per side; 20 bps and an extra minute
of entry latency are separately reported stress cases. Full raw results:
`research_runs/quantum_kernel/results.json` (ignored, local artifact).

### Primary outcomes: profit target +0.4%, exit within 60 minutes

| Kernel | Probability threshold | Active days | Winning active days | Net USD |
|---|---:|---:|---:|---:|
| Classical RBF | 0.50 | 148 | 54.05% | -476.02 |
| Quantum fidelity | 0.50 | 148 | 47.97% | -600.94 |
| Classical RBF | 0.65 | 70 | 55.71% | -198.80 |
| Quantum fidelity | 0.65 | 67 | 49.25% | -254.45 |

Thresholds 0.80 and 0.90 produced no active days, not successful forecasts.
Without the profit target, at threshold 0.50 the RBF model traded four losing
days (-28.94 USD), and fidelity one losing day (-11.83 USD). All 48
kernel/horizon/threshold/cost/latency outcomes failed the screen. This rejects
these particular models, not all quantum or classical learning approaches.

## Limits and next evidence

- Current stock membership creates selection/survivorship bias.
- Bar fills, stops and account guards are approximate, not a tick-level replay
  of the entire production account. Small experimental allocation does not
  prove behavior of a fully allocated account. End-of-day peak reference is
  not a full intraday high-water mark. All entries occur at one fixed time;
  there are no later entries for an intraday entry cutoff to block.
- Costs are assumed, not calibrated from a representative historical quote
  sample. A preliminary paginated AAPL request returned only the first 10,000
  quotes: median full spread about 1.52 bps. It was truncated and is NOT enough
  to lower cost assumptions or represent other symbols, times or market impact.
- Next: measure representative bid/ask coverage and execution assumptions,
  then research features/regime selection. Log all additional trials. Reusing
  these historical dates cannot become independent evidence through renaming.
- Independent forward evidence is absent. Earliest proposed start October 12
  is a proposal, not proof that collection is running or a model is deployed.

Verification: 212 local tests passed, including normalization/PSD of the
fidelity kernel, invariance of existing predictions to changes in future
candidate rows, chronological date separation, conservative stop/target
ordering and portfolio caps. These verify implementation, not profitability.

## Completed quote-cost pilot

`quote_cost_audit.py` fetched 353,118 SIP quotes across 72 fixed 30-second
assessment windows, with a 10-second seed interval. All 72 requests completed
pagination (86 API pages). Symbols: AAPL, NVDA, TSLA, JPM, DIS, QQQ. Dates:
2025-03-03, 2025-09-02, 2026-04-01, 2026-09-23; NY times 09:45, 10:00, 15:55.
These handpicked windows are a limited diagnostic, NOT a representative
execution study. Raw responses and hashes are preserved locally in ignored
`research_runs/quote_cost_audit/`; no strategy costs were changed.

For each window, spreads are weighted by elapsed quote duration, not update
count. Crossed/invalid quotes interrupt coverage. Quotes older than two seconds
are excluded conservatively: this freshness rule does not prove data outages,
since an unchanged valid NBBO can persist without a new update.

| Symbol | Median of window median full spreads, bps | Largest window p95, bps | Minimum fresh coverage |
|---|---:|---:|---:|
| AAPL | 1.57 | 8.32 | 100.00% rounded |
| NVDA | 1.15 | 5.89 | 100.00% rounded |
| TSLA | 2.67 | 14.71 | 100.00% rounded |
| JPM | 6.04 | 16.19 | 79.11% |
| DIS | 4.00 | 15.68 | 83.26% |
| QQQ | 0.61 | 3.37 | 100.00% rounded |

The full spread is not a per-side total execution cost. Half-spread estimates
depend on using midpoint as benchmark and on executable size; delay, market
impact, fees and commissions are not captured. In particular, 10 bps per side
is often conservative versus quoted spread, but cannot be replaced by the
smallest observed spread to obtain a profitable backtest. Next research must
separate prediction quality from cost sensitivity and retain stress outcomes,
then test independently with frozen rules and actual execution evidence.

Verification now: 218 local tests passed. Six additional quote tests check
complete pagination, rejection of repeated tokens, freshness/invalid-quote
coverage, time weighting, and missing data not being treated as zero cost.
