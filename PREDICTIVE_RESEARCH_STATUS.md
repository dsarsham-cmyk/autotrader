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

## Fixed-trade gross/net decomposition

Added `fixed_trade_cost_diagnostic.py` and explicit simulated quantities,
raw entry/exit prices and cost drag to portfolio trade records. Repeated the
same experiments into separate ignored `*_accounting` directories. Verified
all 240 original outcomes have exactly unchanged active-day counts and profit
figures (largest difference zero USD). This changes evidence, not decisions.

Accounting sensitivity keeps original fills, sizes, price paths and exits
fixed, varying only the charged per-side cost through 0, 1, 2, 5, 10 and 20 bps.
It is NOT a executable lower-cost strategy replay: lower costs could change
calibration, fills, quantities, subsequent equity and guard actions. Zero-cost
outcomes cannot be promoted. The input artifacts are hashed in
`research_runs/cost_diagnostic/results.json`.

There are 80 primary model/horizon/time/threshold configurations. Of the 20
configurations with at least 30 active days, none reaches 90% even at zero
cost; maximum is 66.67%. Three configurations have slightly positive gross
profit, including duplicate trades at different thresholds; that is not three
independent discoveries. Thirty active days is only a descriptive filter,
NOT the validation minimum or evidence of statistical significance.

For target-within-60-minute kernels at threshold 0.50:

| Model | Active days | Gross USD | Assumed cost drag USD | Net USD | Zero-cost winning days |
|---|---:|---:|---:|---:|---:|
| Classical RBF | 148 | -41.91 | 434.12 | -476.02 | 61.49% |
| Simulated quantum fidelity | 148 | -160.86 | 440.08 | -600.94 | 57.43% |

Conclusion for these tested rules: execution assumptions contribute
substantially to losses, but eliminating them does not establish a sufficient
predictive edge or the target. Next model work needs new defensible signal
inputs and regime/abstention evaluation, not mere architecture substitution.
Forecast probability of any profit must also be assessed alongside expected
profit and downside magnitude; a high win rate alone is not enough.

223 tests pass, including gross/net reconciliation, cost monotonicity on fixed
trades, missing-evidence rejection and abstention not being counted as wins.
No deployment, automatic promotion, budget changes or real money used.

## VWAP/volume/regime and payoff forecasts

Added `regime_predictive_research.py`. Fixed experiment before its first run:
decision after 30 completed minutes; +0.4% price target, exits within 60
minutes or by end of day; baseline versus ten additional opening VWAP,
path-efficiency, realized-volatility, historical same-window volume, prior
range, recent return/volume, dispersion and breadth features. All current-day
features stop at the decision minute. Prior volume/ranges are appended only
after that day's signal. VWAP uses OHLC typical-price approximation.

Three past-fitted boosted forecasts: probability of net positive return,
expected net return and 10th percentile of net return. Separate recent past
calibration fits probability scaling, mean residual offset and a fixed 10th
percentile residual correction. Thresholds 0.65 and 0.90 were fixed in advance.
Compare probability alone versus additionally requiring expected return >0
and Q10 >-1%. This distribution gate is not an increase of existing risk or a
guaranteed stop-loss bound. Portfolio sizing, costs and guards unchanged.

Same 176 exposed exploratory test dates; no independent evidence. Primary
results at probability threshold 0.65 and 10 bps per side:

| Inputs | Exit | Gate | Active days | Winning days | Net USD |
|---|---|---|---:|---:|---:|
| Baseline | 60 minutes | Probability | 81 | 60.49% | -221.10 |
| Extended | 60 minutes | Probability | 69 | 49.28% | -254.52 |
| Baseline | 60 minutes | Mean/Q10 | 5 | 60.00% | -5.13 |
| Extended | 60 minutes | Mean/Q10 | 5 | 60.00% | -7.88 |
| Baseline | Session | Probability | 145 | 48.28% | -725.99 |
| Extended | Session | Probability | 140 | 50.00% | -577.49 |
| Both | Session | Mean/Q10 | 0 | Undefined | 0 |

Probability threshold 0.90 produced no active days. None of 48
configuration/stress outcomes passes the target. Added features do not establish
an advantage; abstention reduces simulated loss but does not establish the
requested trading profitability. Do not select the least-negative configuration
as a successful model. Raw results and dependency/data hashes are in ignored
`research_runs/regime_predictive/results.json`.

227 tests passed. New tests alter post-decision price/volume and future test
candidate features/labels to verify prior signal/forecast invariance. They also
check past-only volume normalization and constant-price VWAP. Technical
correctness is not evidence of a predictive edge.

### Forward data-access requirement verified

Read-only latest-quote API checks on October 10: SIP returned HTTP 403, IEX
returned HTTP 200 (AAPL quote timestamp 2026-10-09T20:36:06.667843082Z, weekend
last available quote). Historical SIP access does NOT establish real-time SIP
entitlement. A SIP-trained opening-volume model cannot silently use IEX live
volume or issue a backdated forecast after delayed SIP data become available.
Before any valid forward test, either train on matching historical IEX inputs
or explicitly simulate the SIP information delay and subsequent decision/entry
times. No subscription purchase/change made; no forward collector or model
deployment claimed. Objective remains unmet.

## Delayed-SIP causal execution experiment

`regime_predictive_research.py --information-delay 15` now trains labels and
calibrates forecasts for the delayed entry, not the original earlier entry.
Features end at session minute 30 (10:00 NY), assumed availability at minute
45 (10:15), simulated entry at minute 46 (10:16). Additional execution-latency
stress enters at minute 47. The publication lag is an explicit assumption,
not a measured guarantee; a future collector must check actual receipt times.
Limits stay frozen from the feature cutoff price while waiting. No retrospective
repricing, historical earlier execution, or real-time SIP entitlement claimed.

Outputs are separate from the zero-information-delay study:
`research_runs/regime_predictive_delay_15/results.json`, 48 configurations,
176 exposed test sessions. Primary probability-only threshold 0.65 results:

| Inputs | Exit | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|
| Baseline | 60 minutes | 96 | 55.21% | -247.39 |
| Extended | 60 minutes | 64 | 60.94% | -135.99 |
| Baseline | Session | 143 | 59.44% | -407.98 |
| Extended | Session | 140 | 55.71% | -419.79 |

Expected-return/Q10 gate yields only one or two active days in the shorter
horizon, both configurations net negative, and none for session exits.
Threshold 0.90 yields no trades. No variant passed the target screen.

Fixed-trade diagnostic now reads the protocol's primary entry delay instead of
silently filtering only delay=1, and preserves feature/gate identity. Separate
output `research_runs/cost_diagnostic/delayed.json`. Extended inputs with
60-minute exit: gross +21.36 USD, cost drag 157.35 USD, net -135.99 USD. At a
hypothetical 2 bps per side on the exact same trades: -10.11 USD and 64.06%
winning days; even at zero costs: 67.19% winning days. These are accounting
sensitivities, not new executable strategies or independent observations.

233 tests passed. Added causality test makes price crash before delayed data
availability and verifies it cannot become an earlier trade/stop; invalid
delay inputs rejected. Added diagnostic regression test ensures delayed
primary outcomes are included and distinct feature/gate identities retained.
Research remains local; no live/real-money activation or risk changes.

## Prospective forecast evidence boundary

Added `prospective_forecast_evidence.py`, a read/write-once local research
boundary, with no model fitting, scheduling or broker/order access. A frozen
manifest binds model bytes, forecast-source bytes, training end date, a
strictly future start date, matched feed, feature cutoff and assumed data lag.
Capture uses the current clock, rejects early/late/backdated submissions,
verifies retained raw-response/calendar file hashes, confirms a calendar
session exists, and requires an exact complete opening-bar packet without
duplicate/future timestamps or unconsumed pagination. Receipt must precede
capture and the hypothetical entry must follow capture. Model/source changes
or duplicate session writes fail rather than silently replacing evidence.

This is not yet an activated forecast collector. No production experiment was
frozen by this turn, no new actual forecasts were recorded, and no real-world
forward observation was added. All test packets and simulated clocks were
temporary test fixtures. Actual training-data provenance and deriving features
and forecasts from retained raw inputs still require collector integration.

Local hashes and clock checks cannot independently authenticate when a file
was created: an external timestamp anchor and independently verifiable raw
receipt provenance are still required. Inspection always reports zero verified
external anchors and independent-validation=false; a local caller-editable
flag cannot be treated as authenticated evidence. Even timestamp-authenticated
forecasts would not by themselves prove executable profitability or 90% wins.

Existing `research_forward` is a DIFFERENT frozen ORB after-close replay, not
the predictive models. Current summary shows five sessions October 5–9,
zero filled trades, zero profit. It supplies no winning active days and must
not be reported as a successful forecast or production execution test.

249 local tests pass. Sixteen new boundary tests cover exclusive recording,
early/late/backdating rejection, future training, feed mismatch, invalid/raw
receipts, future raw bars, changed models/sources and tampering. Remaining work:
fit and identify explicit research control artifacts; integrate a read-only
collector with real receipt times and an external anchor; record genuinely
future predictions and outcomes. Failed models stay research controls, not
automatically promoted trading candidates. Objective remains active/unmet.

## Fitted prospective control and local collector integration

Refactored regime fitting into `fit_forecasters` / `predict_forecasters` without
changing the existing forecasts wrapper. Added `prospective_model_collector.py`
with explicit `freeze`, `collect`, and `inspect` modes. All HTTP calls are GET:
SIP opening bars and paper-account exchange calendar only, never orders.

Actually fitted one EXTENDED/target-60 delayed-SIP control, not selected as a
profitable trading candidate. Artifact is explicitly marked prior-exploration-
failed-target and research-control-only. All labels use entry delay 16 minutes;
training ends July 8, calibration July 9–October 1, final training/calibration
rows 3,361 / 598. Forward start October 12. Artifact size 440,970 bytes.
Local ignored directory: `research_runs/prospective_control_v1`.
Manifest SHA256:
`52ec2c2ae32d0cda998f0046a1a4ee3b09e7b614cf6b4f3f66103f3b57439cf3`.
Artifact SHA256:
`b6a15150f4a87407d2709503e1eebe057a2f51b62fbfc9de7c6216ed742318e1`.
Checked current artifact and all frozen source hashes match.

Collector verifies model hash before joblib loading, scikit-learn version and
feature schema, complete 20-stock current opening context, strictly prior
history, raw packet chronology, data receipt and capture deadline. Final
packet includes probability/mean/Q10 forecasts, not buy/sell commands. Every
forecast is still explicitly unapproved for production. Any missed deadline
fails instead of backdating. No actual future session recorded today:
`inspect` reports 0 sessions, 0 verified external anchors, validation=false.
An actual Saturday collection invocation correctly refused BEFORE API requests
or deserializing the artifact. That is a negative-boundary check, not collection.

Downloaded a SEPARATE history cache `cache/prospective_history_v1` for June 1–
October 9, with SIP/raw metadata and hashes. All 20 symbols have last complete
session October 9; complete-session counts range 86–92. Original training
cache/model was not updated. A schema smoke test using HISTORICAL opening bars
only produced 20 rows x 21 features; it was not recorded as October 12 evidence.

Example manual collection, only in the allowed 10:15–10:16 NY window:
`.venv/Scripts/python.exe prospective_model_collector.py collect --data cache/prospective_history_v1`.
History must be refreshed before subsequent sessions, not silently reused.

254 local tests pass, including live-prefix/offline feature equivalence,
strict prior-history/universe/OHLC validation, no API/deserialization outside
the collection window, and absence of order clients/HTTP write methods.
Remaining gaps: collector is not scheduled or hosted, source manifest uses
local absolute paths/byte hashes, raw historical context provenance is not yet
bound into captured receipts, and externally authenticated timestamps plus
outcome/execution reconciliation are still absent. Do not claim cloud readiness,
running forward collection, profitability, independent validation or 90% wins.

## Portable cloud experiment v2 — prepared October 10

Prepared `research_prospective/control_v2` with the SAME fitted research-control
weights and artifact hash as local v1, not a new successful model. Manifest
uses repository-relative forecast sources and normalized Python LF hashes;
market inputs/artifact hashes remain byte-exact. It additionally requires
retained historical feature-input CSV hashes in every receipt. V1 is retained
as an earlier local prototype; changed code correctly invalidates its source
checks rather than rewriting that old manifest.

V2 manifest SHA256:
`120ce320b515f989524bdcdb489d1dc690f81ea69d1966392a54b450b1749c06`.
Collector and model are research-only, forecast start October 12, zero future
observations. `requirements-prospective.txt` isolates and matches artifact
dependencies without changing production `requirements.txt`.

`predictive-prospective.yml` prepares a separate read-only GitHub Actions job
before the 10:15 NY data-availability window, with summer/winter UTC alternatives
and a DST-aware local-time guard. It does not share production concurrency,
retrain, write repository contents, deploy Railway, submit broker orders or
auto-promote a model. It rejects missing/late data instead of backfilling.
GitHub scheduled jobs can be delayed or dropped: scheduled workflow is not
proof of successful forecast collection.

Public artifact contains forecast hashes/predictions and classified status,
not raw provider bars or historical CSVs. Raw evidence is AES-GCM encrypted in
a separate artifact after the time-sensitive forecast timestamping step. The
key is domain-separated SHA256 of the existing high-entropy Alpaca secret;
that secret is never logged or stored in repository files. The user must retain
the relevant old secret to decrypt archives after credential rotation. Upload
retention is 90 days, not indefinite persistence. External verification must
check GitHub artifact creation time and contents/hash versus the hypothetical
entry; do not infer an authenticated early anchor from a local captured time.

Local checks: 262 tests pass; environment/model/hash validation succeeded;
Saturday plan correctly returned false. Encryption roundtrip and tamper
rejection tested with a fake key. Validation-only mode collects zero forecasts.
Railway read-only status showed CLI-upload source=null, current October 7 engine
deployment unchanged. Cloud publication/dispatch result must be recorded after
verification; this preparation alone is not a completed live forward test.
