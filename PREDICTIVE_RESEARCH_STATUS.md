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

### Cloud publication and validation verified

Published on main, commit `1365f9a6efa87210fd9b3e053d4195f191ebc178`.
GitHub workflow ID 380564964 returned state ACTIVE. Manual validation-only
dispatch returned HTTP 204; specific run 38058605995 completed SUCCESS:
https://github.com/dsarsham-cmyk/autotrader/actions/runs/38058605995

Linux installed isolated dependencies, matched the frozen model/source hashes,
and loaded the own sklearn artifact successfully. Collection step was SKIPPED.
Downloaded artifact 11671084251, created 2026-10-10T14:11:39Z, and inspected
`research_runs/cloud_status.json`: environment validation only, orders=false,
production-approved=false, recorded-sessions=0, exact artifact model hash
`b6a15150f4a87407d2709503e1eebe057a2f51b62fbfc9de7c6216ed742318e1`.
This authenticates an environment check, NOT a future forecast, trade, win or
readiness verdict. Encrypted-data collection steps were correctly skipped.

Workflow checkout is pinned to this validated source commit so later unrelated
research edits cannot silently mutate or invalidate the experiment. Any new
model/source protocol must be a separately identified experiment, not updates
to v2 evidence. GitHub's workflow SHA identifies workflow configuration; pinned
checkout/ref and frozen source hashes identify actual forecast code.

Read-only Railway status AFTER publication confirms same engine deployment
94d8114f-563c-4027-8fa0-7e9be70e8183, SUCCESS, created October 7; source remains
null (CLI-upload). No trading engine deployment or restart occurred.
First eligible scheduled collection attempt is Monday October 12; exact timing
is not guaranteed by GitHub. Future forecast collection, timely external anchor,
profitability, risk behavior and 90% wins remain unverified. Goal not complete.

## Outcome/anchor auditor and retained artifact backup

Added `prospective_outcome_audit.py`, separate from pinned forecast sources, so
v2's predictive protocol/model is not mutated. The CLI reads GitHub API only,
checks run identity and terminal state, paginates artifacts/jobs, verifies ZIP
SHA256 against GitHub's artifact digest, and saves unchanged local backups.
An existing different archive is never overwritten. This allows retention
beyond the 90-day GitHub artifact window, but requires running backup retrieval
before remote expiration; it is not yet an automatic archival service.

Anchor checks do NOT equate artifact creation time with completed upload.
They require the successful upload step's server-reported completed_at from
the run's jobs API. Conservative timestamp upper bound is completed_at + one
second, and it must precede the exact frozen hypothetical entry. Late or
missing completion confirmation is not timely forward evidence. Date, feed,
feature cutoff, receipt/capture and frozen-entry chronology are also checked.

Pure single-session simulated evaluator checks original 30-minute opening
input against complete outcome arrays, rejects changed/invalid OHLCV, and
replays the fixed .65 threshold, target-60 timing and 10/20-bps/extra-latency
cases. It reports gross/net decomposition, no-trade days and category/stock/
position-cap checks. It does NOT yet decrypt raw cloud archives, derive/recheck
model features against retained history, retrieve validated future outcome
timestamps automatically, or cumulatively replay capital across sessions.
It does not claim broker execution or whole-account risk validation. All
validation/production-approval flags remain false.

Real verification on run 38058605995: downloaded artifact 11671084251; both
GitHub and actual ZIP digest equal
`sha256:2d9b5e646575b72a17bd2ca7712ca5b3fc93b20d872a325f661f0136e62ccd14`.
Upload job 114232076911 completed timestamp step at 2026-10-10T14:11:39Z.
Saved ZIP, server metadata and inspection in ignored
`research_runs/prospective_backups/38058605995/`. Its forecast count and timely
forecast-anchor count are BOTH ZERO: it is still only an environment check.

271 local tests passed. Nine new tests cover synthetic target/no-trade
accounting, rejecting late upload despite early artifact creation, fixed entry
chronology, original-input prefix changes, nonprospective dates, ZIP digest
tampering and write-once backup behavior. Synthetic 100% on one fixture is
explicitly not independent validation. No new actual forecast, winning day,
profit or paper order was produced. Objective remains unmet.

## Full input reproduction and dedicated evidence encryption

Added `prospective_full_audit.py`: verifies retained raw-data hashes, reconstructs
historical inputs, reproduces all published probability/mean/Q10 predictions
with the frozen model, and obtains complete after-close SIP outcomes for the
single-session simulated evaluator. No orders or production approval. Actual
environment-check run still contains zero forecasts and zero evaluated sessions.
A roundtrip using the real frozen model and a synthetic packet passed; it is
software verification, not prospective performance. Cumulative capital replay,
automatic after-close auditing and broker execution validation remain absent.

Security correction: current Alpaca paper secret was verified to remain in the
public HANDOFF and its history. Broker-secret-derived encryption is therefore
NOT confidential. No actual private forecast archive had been produced with it.
New `research_evidence_crypto.py` uses a separate random 256-bit key, provisioned
as GitHub secret PROSPECTIVE_EVIDENCE_KEY and protected locally with Windows
current-user DPAPI. There is no broker-secret fallback. The workflow uses this
separate helper without changing pinned forecast sources or model. The local
DPAPI copy requires the same Windows profile; recovery arrangements remain to
be established. Broker credentials have NOT been rotated; explicit approval
was requested separately. Public credential exposure remains unresolved.

282 local tests passed. Cloud validation run 38060365417 completed successfully:
https://github.com/dsarsham-cmyk/autotrader/actions/runs/38060365417
Dedicated-key validation and frozen-model environment validation passed on
Linux. Forecast collection and private archive sealing were skipped in this
validation-only run; it does not verify a real cloud encryption/collection run.
No new genuine forecast, profitable day or independent validation was obtained.

## Cumulative audit and recent retrospective control check

Added `prospective_series_audit.py`. It calls the remote digest/anchor/decrypt/
input reproduction chain for each specified run, records a completed exchange
calendar, rejects duplicated sessions, and passes all accepted days together
through the unchanged frozen simulator. Capital is not reset between days.
Missing market sessions are gaps, not inactivity or wins. Half-days remain
unsupported and visible as gaps. It reports net/gross costs, end-of-day drawdown,
conservative adverse mark versus prior EOD peak, losing observed-session streak,
budgets, planned risk and probability reliability conditional on modeled fills.
Stock rows are correlated, not independent trading-day observations. The pure
evaluator does not authenticate callers; the CLI performs the provenance chain.
No performance screen grants trading permission. It is still a virtual small
sleeve, not a replay of the entire production account or an intraday peak guard.
Automatic auditing and durable archival beyond GitHub retention remain absent.

Removed the old broker-derived-envelope decryption path entirely. Full auditing
uses only the dedicated evidence key; it no longer requires a broker secret
to decrypt. Broker credentials are still unchanged pending rotation approval.

Real cumulative audit of runs 38058605995 and 38060365417 authenticated and
backed up both ZIPs, including artifact 11672633478 from the latter. Both are
environment checks: ZERO prospective predictions/evaluated/active sessions,
zero profit, performance screen false. Before forward start October 12, the
calendar guard correctly performs no broker calendar request.

New `frozen_control_retrospective.py` checks the existing model, without fitting
or selecting thresholds, on October 5-9 cached SIP data. It is EXPLORATORY:
model created October 10 after these observations; dates were already exposed.
October 6 lacks a complete CVX session and is explicitly excluded, not counted
as a no-trade day. Remaining four days generated 80 candidate predictions.

| Assumed per-side cost | Extra entry delay from minute 30 | Active days | Winning active days | Simulated net USD |
|---|---:|---:|---:|---:|
| 10 bps | 16 minutes | 4 | 75.0% | -0.112576 |
| 20 bps | 16 minutes | 2 | 0.0% | -0.017609 |
| 10 bps | 17 minutes | 3 | 66.7% | -2.182664 |

Primary daily results: October 5 -6.110275, October 7 +1.273787,
October 8 +1.604345, October 9 +3.119567 USD. These are NOT the paper broker's
actual daily account results. The fixed model's assumed-fill candidate Brier
score was .234658 over 33 filled candidates; only nine filled candidates had
p>=.65, none p>=.80. Tiny/correlated samples do not establish calibration.
Raw results/hashes retained in ignored `research_runs/frozen_control_retrospective/`.
This is further evidence that a high winning-day percentage alone is not profit.

295 tests passed, including cumulative losses changing subsequent whole-share
sizing, missing/duplicate/no-trade sessions, late anchors, probability errors,
legacy envelope rejection and future path invariance of retrospective features.
Frozen predictive source hashes still match. No engine deployment, order,
leverage change, risk relaxation or model promotion occurred. Goal remains unmet.

## Two-stage daily-basket forecasting: tested, not promoted

New hypothesis in `daily_meta_research.py`: predict profit of the entire selected
daily basket instead of relying only on individual stock probabilities. Stage
one is a boosted stock classifier with strictly earlier training/calibration
dates (120-date warmup, last 40 dates for calibration, 20-date future blocks).
It is calibrated conditional on historical simulated fills; future candidates
are never prefiltered by their eventual fills. Meta labels use the cumulative
base policy on these cross-fitted forecasts, not in-sample stock predictions.
The second model uses opening features and stock scores, never current fills
or future P&L. It fits only earlier active-date labels with a separate 30-date
calibration block. Logistic and boosted day classifiers are compared at fixed
.65 and .90 gates. Missing fit evidence is an abstention, not a win. The gated
policy can have different share counts from the base-policy meta labels.

First dataset (2025-2026): 176 outer test sessions, 15 stock cross-fit folds,
296 meta-history dates, 89 base-active history dates. Primary unfiltered result
84 active days, 55.95% wins, -208.01 simulated USD. All four gates produced
zero active days: 6 of 9 meta folds lacked sufficient past active calibration
evidence, and the later forecasts did not generate filled gated orders. Zero
activity is failure to establish the target, not 100% profitable days.

To test whether sample scarcity caused this failure, fetched 3,138,245 new SIP
minute bars for the same 20 stocks over 2024. These are owned historical API
downloads, with SIP/raw metadata and byte hashes, in ignored
`cache/daily_meta_sip_2024/`. `daily_meta_dataset.py` joins them with the untouched
original cache into `cache/daily_meta_extended/`. It checks feed/adjustment/hash,
retains source metadata, sorts timestamps, deduplicates identical observations
and rejects contradictory overlapping revisions. Original data, trained frozen
model and prospective experiment were NOT changed. Raw split discontinuities
remain a feature-quality limitation; no overnight simulated gains are invented.

Extended dataset: 28 stock cross-fit folds, 547 meta-history dates, 216
base-active history dates and 427 outer test sessions. The same fixed protocol
produced these primary 10-bps-per-side, 16-minute-delay outcomes:

| Daily model/gate | Active days | Winning active days | Simulated net USD |
|---|---:|---:|---:|
| Base stock model, no day gate | 165 | 62.42% | -465.62 |
| Logistic day gate >=.65 | 55 | 56.36% | -219.43 |
| Boosted day gate >=.65 | 57 | 56.14% | -217.60 |
| Either day model >=.90 | 0 | not defined | 0.00 |

13 of 22 meta folds could fit; 9 lacked sufficient past evidence. Maximum day
forecast was .8353 logistic/.8396 boosted, not .90. Lower absolute loss with
gates mostly reflects fewer trades; winning-day accuracy worsened, so it is
NOT a demonstrated predictive improvement. Additional-minute stress losses
were -290.76 logistic/-289.69 boosted; 20-bps stress losses -368.40/-372.79.
At 20 bps per side, the fixed +.4% gross target itself nets slightly negative
after multiplicative costs, an explicit limitation of this stress case.
All 30 outcomes across the two datasets failed the research screen. Primary
extended baseline Wilson interval was 54.83-69.45%, far below the target.
All simulated allocation/position/planned-risk checks passed; that still does
not prove whole-account production risk behavior or actual broker execution.

Results/provenance retained in ignored `research_runs/daily_meta/` and
`research_runs/daily_meta_extended/`. All historical dates are exploratory and
exposed; no new independent future observation or profitable strategy exists.
307 tests passed, including stock/meta chronology, future-label/activity
invariance, no filtering of future nonfills, future-feature isolation and
contradictory cache-overlap rejection. No orders, engine deployment, risk-limit
change or promotion. Next research needs materially different predictive
information, not relabeling abstention or lowering the required success rate.

## New information: historical displayed-quote microstructure, matched ablation

Research motivation: queue imbalance can carry information about the NEXT
mid-price tick, not automatically a profitable hour-long delayed trade. Primary
source accessed October 10, 2026:
https://arxiv.org/abs/1512.03492 (Gould/Bonart, Queue Imbalance as a One-Tick-Ahead
Price Predictor). Historical API behavior/quote fields checked against Alpaca:
https://docs.alpaca.markets/us/reference/stockquotes-1 and
https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data.
The API's inclusive end requires cutoff minus one nanosecond; every response
page is checked rather than treating an initial page as complete.

Added `quote_microstructure_research.py`: a GET-only collector and nine features
from the final ten seconds BEFORE 10:00 NY, with two-second seeds. Features
describe time-weighted displayed bid/ask imbalance, spread, weighted-midpoint
pressure, observed midpoint change/volatility and a normalized best-quote flow
proxy. They are NOT full depth, executed order flow or a calibrated fair value.
Conflicting same-timestamp quote states interrupt coverage rather than allowing
arbitrary last-record wins. Quotes at/after cutoff cannot affect features.
Crossed/invalid/stale states interrupt eligibility; terminal quote must be fresh.
Two-second quote-age eligibility is a conservative model rule, NOT proof that
an unchanged exchange quote expired or a broker feed failed.

Fixed request plan persisted before collection: six present-day stocks AAPL,
MSFT, NVDA, TSLA, JPM, DIS; 180 evenly spaced eligible historical dates from
2024-02-01 through 2026-10-01. Retained 564,377 raw historical SIP quotes across
1,080 windows/1,080 complete API pages, 74,761,957 bytes, zero fetch errors.
874 windows met >=90% known-prefix coverage and terminal-freshness rules; 206
were explicitly ineligible. More JPM/DIS exclusions show sampling/eligibility
bias, not an outage. Private raw JSON, request identities, plan, receipt times
and hashes remain ignored in `research_runs/quote_microstructure/`; no quote
data or keys published. Original market caches were unchanged.

`quote_feature_ablation.py` recomputes quote features from byte-verified raw
archives and verifies the original bar hashes/request identities/full collection
before fitting. Bar-only and bar+NBBO arms use IDENTICAL eligible candidates and
date splits. Four chronological test folds span 80 sampled test sessions after
100 warmup dates; calibration uses the immediately prior 30 sampled dates.
Only past simulated fills condition fit/calibration; future candidates are not
prefiltered by eventual fills. Models: logistic, boosted, classical RBF and the
existing four-qubit/two-layer CPU-simulated fidelity kernel. Kernel scaler/PCA
fits past training only; matched quantum/classical projection and max 600 past
train/calibration rows. No hardware/computational advantage is claimed.

Fixed .50/.65/.90 gates, 10-bps cost each side, feature cutoff minute 30,
15-minute assumed SIP publication delay and 1-minute execution latency were
declared before evaluating outcomes. Existing stop/target, 1% stock cap, 5%
category cap and three-position cap stay unchanged. Twenty-bps cost and extra
entry-minute stress are separately reported. No favorable instantaneous-SIP
simulation substitutes for the actual delayed-information constraint.

Primary .50-gate results (same 80 sampled test sessions):

| Model | Features | Active days | Winning active days | Simulated net USD |
|---|---|---:|---:|---:|
| Logistic | bars only | 36 | 50.00% | -108.86 |
| Logistic | bars + NBBO | 35 | 45.71% | -114.71 |
| Boosted | bars only | 37 | 54.05% | -85.68 |
| Boosted | bars + NBBO | 45 | 53.33% | -111.73 |
| Classical RBF | bars only | 34 | 47.06% | -123.79 |
| Classical RBF | bars + NBBO | 49 | 51.02% | -157.63 |
| Simulated quantum | bars only | 39 | 48.72% | -94.80 |
| Simulated quantum | bars + NBBO | 40 | 57.50% | -83.49 |

At .65, quantum bar-only had +9.90 USD/9 active days/77.78% wins, but an extra
entry minute changed it to -5.78 USD/10 active days/50% wins. This is a tiny,
fragile exploratory result, NOT a profitable validated strategy or proof of
quantum advantage. Adding NBBO at .65 gave quantum -2.94 USD/6 days/66.67%
and boosted -.51 USD/5 days/80%. Boosted bar-only gave +1.99 USD on only seven
active days (85.71%); insufficient and not attributable to quote information.
Every .90 gate abstained entirely. All 72 model/feature/gate/stress outcomes
failed the target screen. Allocation/position/planned-risk checks passed for
all simulated cases, not real production execution or whole-account guards.

Results/hashes retained in ignored `research_runs/quote_ablation/`. Sampled,
already-exposed dates, present-day universe, full-session bar exclusions,
historical revisions and unmodeled quote execution conditions remain limitations.
No new independent forward observation exists. It would be wrong to claim that
this experiment disproves all order-book learning: it rejects this small NBBO
feature set under the current delay/horizon/cost constraints. Next hypotheses
must match the signal's usable receipt time and forecast horizon, rather than
pretend the signal is instantly accessible or lower loss limits.

318 tests passed, covering future quote/label isolation, temporal splits,
matched eligibility, quantum kernel routing, invalid/ambiguous/stale quotes,
DST boundaries and rejecting partial collection. Frozen prospective source
hashes still match. No broker orders, deployment, real money, cost reduction,
leverage increase or model promotion. Goal remains unmet.

## Mixed delayed-SIP context plus near-entry IEX quotes: separate protocol

Added `hybrid_iex_research.py`, NOT a feed substitution into the frozen SIP
model. Primary documentation accessed October 10, 2026:
https://docs.alpaca.markets/us/docs/market-data-faq and
https://docs.alpaca.markets/us/reference/stocklatestquotes-1.
IEX is one exchange, not consolidated SIP/NBBO. Read-only account checks returned
HTTP200 for historical IEX quotes and latest IEX quote. Since today is Saturday,
this authenticates ACCESS, not a live regular-session freshness/latency test.
No market-data subscription or broker configuration was changed.

New declared timing: SIP opening context ends 10:00 NY and is assumed available
10:15. IEX quote window 10:15:20-10:15:30 (exclusive end, two-second seed), with
entry no earlier than 10:16. This leaves 30 seconds for actual receipt, inference
and external anchoring; real collector timing remains unverified. Historical
receipt today cannot authenticate the original real-time delivery latency.
New features combine nine IEX quote measures with fresh-midpoint movement versus
the delayed SIP close. BOTH matched arms fix the simulated entry limit to the
same latest known IEX midpoint x1.001. No future open is used to reprice it.
Thus comparison within this study is matched, but comparisons to old frozen
control cannot attribute changes solely to new features: limit policy and
eligibility changed. The frozen model/protocol were NOT modified.

Fixed six-stock/180-date plan inherited from the previous study, not selected
by favorable payouts. GET-only multi-symbol pagination fetched 526,122 IEX
quotes in 180 complete API pages, zero date-fetch errors. Raw pages plus merged
records retained privately (139,005,184 bytes) with identities and byte hashes
in ignored `research_runs/hybrid_iex/`. Of 1,080 stock windows, 366 were usable,
368 lacked conservative fresh-quote coverage and 346 had terminal spread above
the fixed 20-bps ceiling. The ceiling is a BEFORE-decision eligibility rule,
not a reduced execution-cost assumption. IEX sparse/wide quotes do not prove
a broker outage. This protocol is fitted/calibrated on its own mixed-feed
historical inputs; no existing SIP classifier is presented as IEX-compatible.

Four paired model types, fixed .50/.65/.90 gates and the existing 10/20-bps and
extra-minute stress cases produced 72 outcomes, all failing the research target
screen. Four chronological test folds cover 61 eligible sampled test sessions
after 100 warmup dates and 30-date prior calibration blocks. Missing eligibility
does not become a profitable day. Primary .50-gate results:

| Model | Features (both use fresh limit) | Active days | Winning active days | Simulated net USD |
|---|---|---:|---:|---:|
| Logistic | SIP context | 23 | 34.78% | -103.94 |
| Logistic | context + IEX | 26 | 42.31% | -94.11 |
| Boosted | SIP context | 17 | 35.29% | -100.57 |
| Boosted | context + IEX | 26 | 42.31% | -104.39 |
| Classical RBF | SIP context | 33 | 45.45% | -141.80 |
| Classical RBF | context + IEX | 25 | 48.00% | -100.63 |
| Simulated quantum | SIP context | 28 | 46.43% | -101.51 |
| Simulated quantum | context + IEX | 21 | 42.86% | -65.68 |

At .65, quantum+IEX traded six active days, 66.67% wins, -9.08 USD. At .90,
logistic+IEX had a ONE-day +1.9242 USD/100% outcome: Wilson interval 20.65-100%.
Twenty-bps stress did not fill that candidate. A single winning day is not a
90% model, independent validation or a deployable improvement. Other .90
variants were inactive except two bar-context logistic days (50%, -9.84 USD).
All simulated category/stock/position/planned-risk checks passed; whole-account
production guards and actual execution remain unverified by this study.

Results and exact source/input hashes retained in ignored
`research_runs/hybrid_iex_evaluation/`. Existing historical exposure, selected
universe/dates, complete-session bar exclusions, quote conditions/executable
size and original publication latency remain limitations. Evidence rejects
these models/protocol, not every use of fresh single-venue data. Next research
must test economic asymmetry of exits and calibrated net outcomes, not treat
freshness or large model confidence as proof of edge.

327 tests passed, including mixed-feed chronology, nanosecond cutoff, stale/
ambiguous/naive timestamp rejection, all-symbol/all-page IEX retrieval without
fallback, predecision spread eligibility, immutable quote hashes, partial
collection rejection and equal fresh-limit semantics. Frozen prospective source
hashes still match. No deployment, broker orders, real money, cost reduction,
risk-limit relaxation or model promotion. Objective remains unmet.

## Stricter stops with policy-specific retraining — October 10, 2026

Added isolated `tighter_stop_simulator.py` and `tighter_stop_research.py`.
Stops are 1% (reference), 0.5% and 0.25%; widening is rejected. Target remains
0.4%, horizon 60 minutes, SIP information cutoff 10:00 NY, assumed receipt
10:15 and entry 10:16. Four models are refitted/calibrated separately on each
stop policy's past filled-trade labels; test candidates are NOT filtered by
future fills. 240 warmup dates, 60 prior calibration dates, 20-date test blocks
give 22 folds and 427 observed historical test sessions in the extended stock
dataset. These dates were already exposed: NOT independent forward evidence.

Fixed stock/category budgets remain 1%/5%, maximum three positions, planned
trade risk 0.05%, cash-only non-refunding purchase reservation. Existing daily
and permanent guard approximations remain; gap execution may exceed a trigger.
No production strategy/configuration was modified. Primary 0.50-gate results
include 10 bps per side and cumulative virtual starting equity of 100,000 USD:

| Stop | Model | Active days | Winning active days | Net USD | Worst day USD |
|---|---|---:|---:|---:|---:|
| 1% | Logistic | 314 | 55.73% | -1,044.38 | -35.06 |
| 1% | Boosted | 305 | 55.41% | -1,045.08 | -34.53 |
| 1% | Classical RBF | 341 | 48.39% | -1,136.23 | -32.83 |
| 1% | Simulated quantum | 328 | 45.43% | -1,069.59 | -33.18 |
| 0.5% | Logistic | 221 | 44.34% | -752.24 | -20.09 |
| 0.5% | Boosted | 195 | 40.00% | -728.21 | -20.24 |
| 0.5% | Classical RBF | 200 | 36.50% | -755.96 | -19.62 |
| 0.5% | Simulated quantum | 213 | 39.44% | -735.54 | -19.81 |
| 0.25% | Logistic | 2 | 0.00% | -8.62 | -4.35 |
| 0.25% | Boosted | 7 | 28.57% | -25.42 | -12.87 |
| 0.25% | Classical RBF | 11 | 36.36% | -28.38 | -8.64 |
| 0.25% | Simulated quantum | 4 | 25.00% | -10.94 | -4.38 |

Lower loss is not edge: tighter stops changed labels and made models abstain
or lose more often. At gate .65 the 0.5% boosted variant earned +9.81 USD on
only FOUR active days (75% wins). At gate .90 the 1% logistic reference earned
+3.59 USD on only TWO active days (100% wins). Neither establishes the target.
All 108 outcomes (12 stop/model cases, three gates, three cost/timing cases)
failed the screen. All simulated stock/category/position/planned-risk checks,
including the actual tighter-stop planned risk, passed. No daily gap-trigger
overshoot occurred in these historical outcomes; a synthetic severe-gap test
demonstrates overshoot remains possible despite planned-risk compliance.

For exact target/stop exits without gaps, the algebraic TRADE break-even win
rate falls from 85.73% to 77.80% to 69.26%. This is NOT predicted day accuracy.
At 20 bps per side even the 0.4% target nets slightly negative. Cost assumptions
were not reduced to manufacture profitability.

Complete local results: ignored `research_runs/tighter_stops/results.json`,
SHA256 `f55702a093cf5c8856ea83e85f272c7653d9b536713d3206fb1441f9ff64e49c`.
Recorded dependency hashes match current sources. 343 tests passed (four
existing sklearn deprecation warnings), including 16 new tests for stricter
labels, past-only fitting, future-label isolation, reference accounting parity,
stop-first OHLC ordering, gaps, budgets and no-trade handling. Minute-bar fill
assumptions, present-day universe, full-session selection, raw splits and EOD
peak guards remain limitations. Quantum remains a four-qubit CPU simulation.
No orders, deployment, real money or model promotion. Objective remains unmet.
This rejects tighter fixed stops as a sufficient repair of these predictors;
next work must address signal/conditional net-outcome quality rather than
selecting rare historical winning days or relaxing loss limits.
