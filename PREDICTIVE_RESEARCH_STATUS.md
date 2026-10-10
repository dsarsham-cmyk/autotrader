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

## Conditional gain/loss prediction and net-expectancy ranking — October 10

Added isolated `conditional_payoff_research.py`. Unlike the earlier single
mean-return regressor, it learns separate conditional net gain and conditional
net loss magnitudes, then combines them with a past-calibrated classifier:
`expected net = p * E(net | win) - (1-p) * E(loss | non-win)`.
Linear logistic/Ridge and boosted classifier/regressor pairs use basis-point
regression targets and separate past calibration offsets. Conditional heads
require minimum past samples and reject unfilled fitting outcomes. Negative
predicted magnitudes are clipped to zero, not interpreted as favorable losses.
This is an estimate, not a guarantee or a newly measured probability of profit.

Matched selectors: probability-only reference, positive-expectancy filtering
with probability ranking, and positive-expectancy filtering with net-return
ranking. Selection precedes knowledge of fills; an unfilled chosen candidate
is NOT replaced by a retrospectively known fill. All sessions remain visible.
Simulator ranking scores are explicitly ordinal, NOT calibrated probabilities;
original classifier probabilities are retained separately. The probability-only
reference reproduces every corresponding 1%-stop prior study trade and account
result exactly, including cost/latency stress cases. Thus comparisons within
this study do not silently change exits or allocation.

Same delayed SIP timing, fixed 1% stop, 0.4% target, 60-minute holding horizon,
10 bps per side, stock/category budgets and loss guards as the preceding study.
22 folds / 427 historical test sessions / 4,079 filled evaluation candidates.
Two models, three selectors, three probability gates and three cost/timing
variants produced 54 outcomes; ALL failed the target screen. Primary outcomes:

| Model | Selector | Probability gate | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|---:|
| Logistic/Ridge | Probability reference | .50 | 314 | 55.73% | -1,044.38 |
| Logistic/Ridge | Probability reference | .65 | 216 | 60.65% | -729.87 |
| Logistic/Ridge | Positive expectancy, either ranking | .50 / .65 / .90 | 2 | 100% | +3.59 |
| Boosted | Probability reference | .50 | 305 | 55.41% | -1,045.08 |
| Boosted | Probability reference | .65 | 149 | 60.40% | -453.25 |
| Boosted | Positive expectancy, either ranking | .50 | 6 | 33.33% | -16.27 |
| Boosted | Positive expectancy, either ranking | .65 | 2 | 50% | -4.34 |
| Boosted | Positive expectancy, either ranking | .90 | 0 | undefined | 0 |

The logistic reference at .90 already selects the same two winning days.
Their Wilson interval is 34.237%-100%, NOT proof of 90% winning days. Inactive
days are not wins. Both positive-expectancy rankings happened to select the
same actual fills; no ranking improvement was observed. Across all filled test
candidates, expected-return MAE was 45.99 bps for linear and 46.40 bps for boosted,
versus roughly 19.94 bps net return at the exact target without gaps. This
comparison does not prove that no individual signal can work, but shows why
positive model output alone is weak evidence of an exploitable edge here.
Weighted mean prediction bias was -1.33 / -2.24 bps respectively; small overall
bias does NOT validate conditional calibration of the selected tail.

All simulated budget/position/planned-risk checks passed across 54 outcomes.
352 tests passed (four existing sklearn deprecation warnings), including nine
new conditional payoff, chronology, future-outcome isolation, ordinal-score,
no-fill replacement and invalid-input tests. Frozen prospective model and
source hashes still match. Complete ignored local result
`research_runs/conditional_payoff/results.json` SHA256:
`7d3e4888b8685b44a3d6df734f40aceb489ce564d1cc782e2d6f88c67c865b5c`.
All dependency hashes matched after completion. No deployment, orders, real
money, risk increase or model promotion. Existing historical exposure, universe,
full-session selection, raw split and assumed OHLC execution limitations remain.
Objective remains unmet: conditional payoff decomposition did not create enough
accurate, profitable signals. Further research must establish new usable signal
information or a different validated payoff policy, not count rare wins as 90%
evidence or treat software test counts as financial readiness.

## Ordered opening-path AI representation — October 10, 2026

Added `opening_path_research.py`: matched logistic and dense neural-network
classifiers on either the existing 21 summary features or those summaries plus
120 ordered opening-path features (30 minutes x four channels). Channels are
close-to-prior-close log return, log high/low range, log close/open body and
log1p minute volume relative to the SAME minute of 20 PRIOR opening sessions.
No post-10:00 NY price or volume enters today's features. Scalers fit on past
training rows only; probability calibration uses separate later-but-still-past
rows. All future candidates are forecast before filtering actual fills.

The neural model is a conventional dense MLP with learned weights, layers
64/32, alpha10, Adam .001, batch256, seed19, fixed 100-epoch budget, no random
holdout, no validation-based early stopping and no epoch selection from test
profits. It is NOT a transformer, RNN, LLM or quantum computer. The ordered
representation does not itself establish that temporal patterns predict profit.
All 22 neural folds reached the epoch cap with ConvergenceWarning (captured in
the report); thus the evidence tests this bounded configuration, NOT every
neural architecture or a verified converged optimum. Logistic folds had no
warnings. A future training-budget audit should use training-only convergence
criteria rather than selecting epochs by favorable historical trading results.

Same extended historical dataset, 22 folds, 427 test sessions and 4,079 filled
evaluation candidates. The summary/logistic reference reproduces every trade
and account outcome of the corresponding previous reference, including stress
cases. Exit, delay, costs, eligibility and budgets remain matched. Primary:

| Features | Model | Gate | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|---:|
| Summary | Logistic | .50 | 314 | 55.73% | -1,044.38 |
| Summary | Logistic | .65 | 216 | 60.65% | -729.87 |
| Summary | MLP | .50 | 310 | 54.19% | -1,103.87 |
| Summary | MLP | .65 | 167 | 61.68% | -522.26 |
| Summary + ordered path | Logistic | .50 | 319 | 56.74% | -995.13 |
| Summary + ordered path | Logistic | .65 | 147 | 61.22% | -438.96 |
| Summary + ordered path | MLP | .50 | 319 | 56.43% | -1,051.19 |
| Summary + ordered path | MLP | .65 | 247 | 57.89% | -800.80 |

At .90 both neural arms abstained, summary/logistic retained the known two-day
+3.59 USD/100% result, and path/logistic had ONE active winning day/+1.77 USD.
None demonstrates the target. Four feature/model cases x three gates x three
cost/timing variants = 36 outcomes, all failing. Filled-candidate weighted
Brier scores were .243880 (summary/logistic), .244695 (summary/MLP), .246075
(path/logistic), .242229 (path/MLP). The small probability-score improvement
for path/MLP is not an economic advantage: all adequately active primary
variants remain negative after costs.

All simulated budget/position/planned-risk checks passed. 362 tests passed
(four existing sklearn deprecation warnings), including ten new opening
cutoff, same-minute past-volume, ordered-channel, invalid-input, scaler/model/
calibrator future isolation, chronological split and unknown-fill tests.
Frozen prospective source and model hashes still match. Complete ignored local
result `research_runs/opening_path/results.json` SHA256:
`5a45aa35e41337c94f3d7041aaf87c345d91227133f40ace81ed50ed00c60911`.
All dependency hashes match the evaluated code. Historical exposure,
present-day universe/full-session exclusions, raw splits, assumed SIP receipt,
OHLC fills and approximate account guards remain limitations. No orders,
deployment, live money, increased risk or model promotion. Objective unmet;
new neural terminology cannot substitute for accurate profitable predictions.

## Neural training-loss convergence audit — October 10, 2026

Added isolated `neural_convergence_research.py`, preserving the prior evaluated
source and results. Same architecture, initialization seed, input arms, splits,
calibration, trades and budgets; one new declared TRAIN-only stopping policy:
maximum 1,000 epochs, tolerance1e-5, no-improvement patience20, no random holdout
or validation-based early stopping. No epochs were chosen from test P&L.
Official MLP documentation accessed October10:
https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPClassifier.html
and installed sklearn1.9.1 `_update_no_improvement_count` were checked. The
report retains every training loss curve and independently replays its
best-loss/no-improvement rule. A verified training plateau is NOT a global
optimum, calibrated profitability or evidence of market predictability.

All 44 folds reached a verified training plateau with no warnings. Summary
inputs stopped at 65-162 epochs, ordered-path inputs at 99-834 epochs; none
hit the new 1,000-epoch cap. Thus the previous epoch cap was genuinely a
limitation for some fits, but removing it did not create a profitable predictor.
Same 427 historical test sessions / 4,079 filled evaluation candidates. Primary:

| Features | Gate | Active days | Winning active days | Net USD |
|---|---:|---:|---:|---:|
| Summary | .50 | 309 | 54.37% | -1,080.00 |
| Summary | .65 | 183 | 61.20% | -559.96 |
| Summary | .90 | 0 | undefined | 0 |
| Summary + ordered path | .50 | 316 | 58.54% | -944.22 |
| Summary + ordered path | .65 | 248 | 58.87% | -778.20 |
| Summary + ordered path | .90 | 0 | undefined | 0 |

All 18 cost/latency/gate outcomes failed the target screen. The path .50 arm
improved on the 100-epoch neural result (56.43%, -1,051.19 USD) but remains
negative; summary .65 worsened from -522.26 to -559.96 USD. No favorable subset
is promoted. Weighted Brier scores .244477 summary / .242808 ordered path;
training plateau did not imply improved probability quality or economic edge.
All simulated budget/position/planned-risk checks passed. These are not
whole-account production guard or actual fill validations.

369 tests passed (four existing sklearn deprecation warnings), including seven
new tests for plateau replay, finite loss evidence, temporal overlap, invariance
of training loss/epochs to calibration labels and future test features/labels.
Frozen prospective model and source hashes still match. Complete ignored local
result `research_runs/neural_convergence/results.json` SHA256:
`d03c4f53b13e36e695c467c9bb1b90d0ed6793ce49c8d7b0094bf4a50a607473`.
All evaluated dependency hashes matched. Existing exposure, present-day universe,
complete-session exclusions, raw splits, SIP delay and OHLC execution limitations
remain. No orders, deployment, real money, risk increase or model promotion.
Objective remains unmet. This audit removes premature stopping as a sufficient
explanation for failure of this architecture; useful next research must seek
additional causally available signal information, not repeat an epoch/profit
search on the same already-exposed days.

## Premarket context on matched eligible candidates — October 10, 2026

Added isolated `premarket_predictive_research.py`. Reads the existing owned
SIP/raw extended cache (no new broker request), verifying each complete CSV
against its metadata byte hash. Extracts 08:00-inclusive / 09:30-exclusive
America/New_York minute bars with explicit timezone/DST handling, rejecting
duplicate, non-minute, naive or malformed observations. 855,408 observed
premarket bars across the fixed 20-stock cache. Historical bar timestamps do
NOT authenticate original publication/receipt; sparse/revised bars remain a
limitation. The existing delayed-SIP 10:00 cutoff / 10:16 entry is unchanged.

Ten additional features describe premarket return/range/location, distance from
typical-price VWAP, volatility between observed bars, relative window volume
against 20 prior windows, opening price versus last premarket close, opening
close versus premarket VWAP, observed-bar fraction and terminal age. Today's
volume does not enter its own historical benchmark. Eligibility requires at
least five observed premarket bars and last bar starting at/after09:25, prior
window history and positive current/prior volume. Summary-only and augmented
arms have IDENTICAL eligibility. Thus within-study comparison isolates features;
comparison against earlier unfiltered studies does not. Missing context is not
silently replaced by regular-session or IEX data.

12,595 feature rows eligible, 237 sparse/stale, one missing window across all
feature-complete history. The chronological outer test has 427 sessions / 8,348
observed candidates / 8,209 eligible candidates / 4,012 filled eligible outcomes.
All ineligible test rows/sessions are retained as abstention; zero selection
score for missing context is explicitly NOT a forecast probability. Future fill
does not decide eligibility or whether a candidate is forecast. Same trained
linear/boosted classifiers and train-plateau MLP in paired 21-vs31-feature arms.
Both neural arms reached verified train-only plateaus in all 22 folds.

Primary 10bps-per-side, 1%-stop, 0.4%-target, 60-minute results:

| Model | Features | Gate | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|---:|
| Logistic | Matched summary | .50 | 315 | 55.24% | -1,046.25 |
| Logistic | + premarket | .50 | 314 | 56.69% | -1,059.12 |
| Logistic | Matched summary | .65 | 218 | 61.01% | -706.65 |
| Logistic | + premarket | .65 | 219 | 61.64% | -696.47 |
| Boosted | Matched summary | .50 | 319 | 56.74% | -986.47 |
| Boosted | + premarket | .50 | 319 | 55.80% | -964.49 |
| Boosted | Matched summary | .65 | 162 | 58.02% | -481.53 |
| Boosted | + premarket | .65 | 145 | 57.24% | -422.93 |
| MLP | Matched summary | .50 | 321 | 53.58% | -1,162.06 |
| MLP | + premarket | .50 | 324 | 56.79% | -1,088.33 |
| MLP | Matched summary | .65 | 173 | 61.27% | -598.98 |
| MLP | + premarket | .65 | 212 | 62.74% | -653.02 |

At .90 the augmented MLP had two winning active days/+3.56 USD, not validation
of 90%; augmented logistic had two days/50%/-9.44 USD. Matched summary logistic
retained its previously observed two-day +3.59 USD, other .90 arms abstained.
Six cases x three gates x three cost/latency cases = 54 outcomes, ALL failing
the target screen. Premarket context improves some measures modestly, not a
robust profitable edge. All simulated allocation/position/planned-risk checks
passed. They do not certify production execution or whole-account guard behavior.

380 tests passed (four existing sklearn deprecation warnings), including eleven
new DST/cutoff, prior-volume, missing/stale context, source rejection, unknown
future fill, future label and integrated post-cutoff/missing-window invariance
tests. Frozen prospective model/source hashes still match. Complete ignored
local result `research_runs/premarket_predictive/results.json` SHA256:
`3726bce86f1de8fd6e18033246ecc3165236b012de432ca311b40318ba996330`.
Evaluated dependency hashes matched after completion. Historical exposure,
present-day universe, complete-session selection, raw splits and approximate
VWAP/volatility/OHLC/account guards remain limitations. No orders, deployment,
real money, increased risk or model promotion. Objective unmet; these extra
inputs do not demonstrate the required accuracy/profitability. Further work
must address signal and payoff together without turning a tiny selected tail
into an apparent 90% result or claiming an independent test on exposed dates.

## Cross-asset ETF context — October 10, 2026

Added isolated `macro_context_research.py`. Fixed SPY/TLT/UUP/GLD proxies BEFORE
evaluating their contribution, not selected by stock test payouts. Read-only
historical Alpaca SIP/raw requests fetched January2024 through October1,2026:
SPY579,254 minute bars, TLT489,744, UUP169,633, GLD440,430; total1,679,061.
New ignored cache `cache/macro_context_sip/` contains CSVs and feed/time/byte-hash
metadata. Downloader refuses overwrite. No subscription, broker setting or
position was changed. These ETFs are INPUTS, not added trading instruments.

Primary sources accessed October10,2026:
[SPY fund](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy),
[TLT fund](https://www.ishares.com/us/products/239454/TLT),
[UUP disclosure](https://www.sec.gov/Archives/edgar/data/1383151/000119312526083557/uup-20251231.htm),
[GLD fund](https://www.spdrgoldshares.com/usa/gld/), and
[Alpaca feed/entitlement FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).
They support proxy identities and feed semantics, NOT profitable predictability.
TLT price is not an interest rate, UUP is not a spot FX feed and GLD is not
physical gold execution. No causal macroeconomic-announcement model is claimed.

Each proxy contributes ten first-30-minute/past-session features: observed
return/range/location, typical-price VWAP distance, observed-return volatility,
relative opening volume against prior windows, overnight gap, prior five-day
return, prior volatility and opening coverage. Two extra features are stock
opening return/gap minus SPY counterparts, giving 21-vs63 matched input arms.
Missing opening data or insufficient prior closes makes the candidate abstain
in BOTH arms. Sparse proxies use first/last observed opening bars, not invented
09:30 prices; coverage is explicit. At least five observed bars and terminal
bar start at/after09:58 NY are required. Today's 15:59 close is appended only
AFTER today's signal, and its absence does NOT invalidate today's opening.
No post-10:00 input enters today's features. Prior closes affect tomorrow,
not an earlier forecast. Actual original SIP receipt remains unverified.

11,211 eligible / 1,622 ineligible rows across feature-complete history. The
22-fold outer test retains 427 sessions / 8,348 observed candidates, with 7,423
eligible / 3,543 filled eligible outcomes. Missing inputs do not erase sessions
or become winning days. This is a changed sample versus prior studies, so only
within-study matched comparisons isolate ETF context. Stock outcome dates were
already exposed; newly fetched proxy information is NOT independent validation.
Same 1%-stop, 0.4%-target, 60-minute horizon, delayed entry and 10bps-per-side:

| Model | Features | Gate | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|---:|
| Logistic | Matched summary | .50 | 272 | 54.78% | -963.01 |
| Logistic | + ETF context | .50 | 259 | 55.21% | -893.06 |
| Logistic | Matched summary | .65 | 179 | 55.87% | -737.08 |
| Logistic | + ETF context | .65 | 90 | 53.33% | -443.48 |
| Boosted | Matched summary | .50 | 275 | 53.09% | -1,028.77 |
| Boosted | + ETF context | .50 | 276 | 50.36% | -1,012.22 |
| Boosted | Matched summary | .65 | 135 | 55.56% | -531.14 |
| Boosted | + ETF context | .65 | 102 | 50.00% | -416.04 |
| MLP | Matched summary | .50 | 282 | 53.19% | -982.60 |
| MLP | + ETF context | .50 | 265 | 53.96% | -905.52 |
| MLP | Matched summary | .65 | 156 | 57.69% | -505.49 |
| MLP | + ETF context | .65 | 137 | 56.93% | -503.86 |

At .90 augmented logistic has ONE winning day/+1.66 USD; all other arms
abstain. No target evidence. Six cases / 54 gate-cost-latency outcomes all
failed the screen. All simulated budget/position/planned-risk checks passed.
Both neural arms reached verified train-only plateaus in all 22 folds. Weighted
filled-candidate Brier scores worsened with ETF context: logistic .244148 to
.246744, boosted .242665 to .246720, MLP .244915 to .245471. Lower dollar loss
with fewer selected trades does not establish improved forecasting or edge.

389 tests passed (four existing sklearn deprecation warnings), including nine
new DST/cutoff, current future-close/absence isolation, prior-volume, missing
proxy retention and ambiguous-source tests. Frozen prospective model/source
hashes still match. Complete ignored result `research_runs/macro_context/results.json`
SHA256 `774569507f5b3dbda5cc520e65d837c3511c0953a9209595116bebf8cc10ddd5`;
evaluated dependency hashes match. Current-universe/full-session stock selection,
raw corporate-action/distribution changes, historical revisions and OHLC/guard
approximations remain limitations. No orders, deployment, real money, risk
increase or model promotion. Objective remains unmet: these cross-asset proxies
do not supply the required profitable predictive advantage under this protocol.

## Larger reward targets without wider stops — October 10, 2026

Added isolated `reward_policy_simulator.py` and `reward_policy_research.py`.
Predeclared targets0.4% (reference), 0.8%, 1.2%, unchanged stop1%, maximum
60-minute holding horizon, cash-only stock/category caps1%/5%, max three
positions, planned trade risk0.05%, delayed SIP entry and existing guard
approximations. No lower-cost assumption, larger quantity, wider stop or longer
maximum horizon. Nevertheless a larger target can keep a winning trade exposed
longer WITHIN that cap; equal planned limits do not imply identical realized
risk. Gaps may exceed stop/guard triggers; no artificial clipping of losses.

Classifiers are independently refitted/calibrated on each policy's strictly
past filled outcomes. Test predictions/selection precede knowledge of fill;
no replacement with a retrospectively known fill. Linear, boosted, train-only
plateau MLP and four-qubit simulated quantum-kernel models use the same21
features and22 chronological folds /427 test sessions. All66 neural fits reached
verified training plateaus. Quantum stays a CPU simulation, not hardware.
The0.4% reference reproduces corresponding previous account outcomes exactly
for all four models, including the higher-cost/extra-minute stress cases.

Exact target/stop algebra at10bps per side yields TRADE break-even rates85.73%,
66.68%,54.55%. These are not forecast win rates: actual target frequency,
horizon exits, fills and gaps change the distribution. Increasing potential
reward does not itself supply information about which trades will win.
Primary0.50-gate outcomes:

| Target | Model | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|
| 0.4% | Logistic | 314 | 55.73% | -1,044.38 |
| 0.4% | Boosted | 305 | 55.41% | -1,045.08 |
| 0.4% | MLP | 309 | 54.37% | -1,080.00 |
| 0.4% | Simulated quantum | 328 | 45.43% | -1,069.59 |
| 0.8% | Logistic | 177 | 51.41% | -304.96 |
| 0.8% | Boosted | 63 | 41.27% | -315.34 |
| 0.8% | MLP | 28 | 46.43% | -156.42 |
| 0.8% | Simulated quantum | 38 | 34.21% | -181.45 |
| 1.2% | Logistic | 21 | 42.86% | -44.76 |
| 1.2% | Boosted | 12 | 25.00% | -49.31 |
| 1.2% | MLP | 0 | undefined | 0 |
| 1.2% | Simulated quantum | 9 | 0.00% | -112.09 |

At0.65, target0.8% logistic traded16days/37.5%/-73.99USD, boosted1day/0%/
-11.47USD, MLP abstained, quantum2days/0%/-40.03USD. Target1.2% logistic
traded one losing day/-4.15USD; other0.65 arms abstained. All larger-target0.90
arms abstained. The old reference's two-day+3.59USD/100% remains insufficient.
12cases x3gates x3cost/latency variants =108outcomes, ALL failing the screen.
All simulated allocation/position/planned-risk checks passed, not actual
production execution. Better algebra and lower dollar loss from abstention
did not deliver either the90% goal or a demonstrated profitable strategy.

402 tests passed (four existing sklearn deprecation warnings), including13new
tests for fixed-policy validation, reference parity, changed-label refitting
through all model routes, post-horizon exclusion, stop-first/gap accounting,
equal quantities/limits and future-outcome isolation. Repeated SVC deprecation
warnings also occurred during historical quantum fits; not trading errors or
proof of model validity. Frozen prospective model/source hashes still match.
Complete ignored local result `research_runs/reward_policy/results.json`
SHA256 `2074fa88a8c057d760940aa27ae8ecaf6ad0b6e4e4fc9c177abb3ea3fe062af3`;
evaluated dependency hashes matched. All historic outcomes exposed; target
experiments are exploratory, not independent observations. Fixed-universe,
complete-session selection, raw splits/revisions, assumed receipt, OHLC fills
and EOD-peak guard limitations remain. No orders, deployment, real money,
increased limits or model promotion. Objective remains unmet; changing reward
targets alone is not a sufficient repair of these forecasting models.

## Own-feed IEX bar prediction and one-minute entry — October 10, 2026

Added isolated `iex_bar_predictive_research.py`. Historical GET-only collection
fetched4,963,844 IEX/raw minute bars for all20 existing stock symbols, Jan2024
through October1,2026;399,154,798 CSV bytes retained privately in ignored
`cache/iex_bar_context/` with exact hashes/request metadata. No subscription,
account setting or order was changed. Downloader refuses existing-file
overwrite, contradictory overlapping bars and silent feed fallback.

Primary documentation accessed October10:
[Alpaca feed FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) and
[real-time bar semantics](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data).
Free real-time IEX is one exchange, not consolidated SIP. Historical bar
revisions and timestamps do not authenticate original receipt. Receiving the
complete context, computing and externally anchoring a forecast between10:00
and10:01 remains UNVERIFIED; this research does not claim a working live-feed
collector or compatibility with the existing frozen SIP forecast model.

Sixteen inputs use ONLY own IEX opening/prior-session observations: observed
return/range/location/VWAP/volatility/relative volume, gap/prior returns,
opening coverage, last-five observed return/volume, prior-terminal age and
cross-sectional mean/breadth. At least24 opening bars and terminal bar
starting09:59 are required; sparse/stale windows abstain. Prior last closing
observations must be15:55-or-later. No synthesized missing prices. Today's
closing bar is appended after today's features; its absence cannot disqualify
the current opening. IEX market features are calculated independently of later
SIP completeness. SIP is used solely for simulated outcome prices/fills, not
as a feature or a substitute for missing IEX volume.

Both timing policies are fitted/calibrated on their OWN past labels: entry
minute31(10:01NY), versus46(10:16NY), with60-minute horizon. Timing changes the
holding window and fill distribution as well as signal age, so differences
cannot be attributed solely to latency. Same stock/category/quantity/stop and
cost limits. Match predecision input eligibility; retain ineligible days as
abstention, not wins.12,240 eligible /593 sparse-or-stale /20 missing session
rows across feature-complete history.22 outer folds /427 test sessions /8,348
observed candidates /8,072 eligible test candidates.3,976 fresh and3,916 delayed
filled eligible outcomes; different fills are not erased by matched eligibility.

Primary0.50-gate results, costs10bps each side, stop1%, target0.4%:

| Entry delay | Model | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|
| 1 minute | Logistic | 312 | 56.09% | -1,137.23 |
| 1 minute | Boosted | 309 | 51.13% | -1,206.05 |
| 1 minute | MLP | 309 | 51.46% | -1,227.00 |
| 1 minute | Simulated quantum | 328 | 43.29% | -1,149.76 |
| 16 minutes | Logistic | 311 | 56.59% | -1,065.92 |
| 16 minutes | Boosted | 325 | 50.46% | -1,135.49 |
| 16 minutes | MLP | 313 | 54.95% | -1,077.37 |
| 16 minutes | Simulated quantum | 335 | 46.87% | -1,120.46 |

At0.65, fresh logistic251days/56.57%/-889.11USD; delayed221days/59.28%/
-705.28USD. Fresh MLP209days/56.46%/-769.11USD; delayed166days/59.04%/
-607.65USD. All adequately active outcomes remain negative. At0.90 fresh
logistic9days/66.67%/-21.17USD, delayed logistic7days/71.43%/-14.12USD;
delayed MLP had ONE winning day/+1.66USD, other arms abstained. None proves90%.
Eight cases x3gates x3cost/latency variants =72outcomes, ALL failing the screen.
All simulated budget/position/planned-risk checks passed. All44 neural fits
reached verified train-only plateaus. Quantum fits retained existing SVC
deprecation warnings in report metadata; they are not production trading errors.
Quantum is a four-qubit CPU simulation, not hardware.

411 tests passed (four existing sklearn deprecation warnings), including nine
new own-feed feature isolation, future-close/absence isolation, independence
from future SIP completeness, sparse/stale abstention, SIP-cache rejection and
separate timing-policy label-refitting tests through all model routes. Frozen
prospective model/source hashes still match. Complete ignored local report
`research_runs/iex_bar_predictive/results.json` SHA256:
`002795724765aa8a1aa05a9d0042ba331df0f37ea401970fa4c0826d0c2302ae`.
Evaluated dependency hashes matched. Previously exposed stock outcome dates
remain exploratory even with newly collected inputs. Fixed-universe/full-SIP-
session selection, raw splits/revisions, venue sparsity, unverified live receipt
and OHLC/EOD-peak guard assumptions remain limitations. No orders, deployment,
real money, increased limits or model promotion. Objective remains unmet: the
coherent IEX feed and faster entry do not suffice to make these models profitable.

## 2026-10-10 — No-forecast selection benchmark

Added `predictive_null_benchmark.py` to test whether fresh-IEX model ranking
adds value beyond selection without a forecast. This is NOT another promoted
strategy or independent validation. Exact original source/input hashes were
checked; all twelve fresh-entry model/gate outcomes and trades reproduced the
completed IEX study. Same 427 exposed sessions, entry delay one minute, stop
1%, target 0.4%, 60-minute horizon, costs 10bps per side and existing budgets.

Five fixed seeds (11,23,37,53,71), with every result retained and no best-seed
choice, deterministically hash date/symbol to select at most three candidates
BEFORE fills. No replacing an unfilled selection using future knowledge.
For each model/gate, controls rank only that model's eligible probability-gated
pool; these test ranking, NOT the value of the gate. Five additional controls
select from all eligible candidates without using model probabilities; their
different coverage/fills mean they are not identical-coverage ranking tests.
Ordinal selection scores are explicitly NOT forecast probabilities.

Primary 0.50-gate ranking comparison, cumulative simulated USD:

| Model | Model net | Mean of five pool controls | Mean daily advantage, bps | Descriptive interval, bps |
|---|---:|---:|---:|---:|
| Logistic | -1,137.23 | -1,183.66 | 0.0110 | [-0.0496, 0.0733] |
| Boosted | -1,206.05 | -1,140.56 | -0.0155 | [-0.0622, 0.0300] |
| MLP | -1,227.00 | -1,197.46 | -0.0070 | [-0.0615, 0.0480] |
| Simulated quantum | -1,149.76 | -1,213.64 | 0.0151 | [-0.0399, 0.0651] |

The 0.65-gate intervals also include zero. At 0.90, most models abstain;
logistic and its pool controls have identical -21.17 USD outcomes. Tiny
floating-point differences around 1e-18bps are numerical zero, not an edge.
Intervals use paired per-session returns against the five-control mean and a
fixed 20-observed-session circular block bootstrap with 1,024 replicates.
They are descriptive, not proof of equivalence, stationarity, causality or
correction for repeated research. Seeds are not independent market days.

All-eligible controls, each on the same observed sessions:

| Seed | Active days | Winning active days | Net USD |
|---|---:|---:|---:|
| 11 | 357 | 45.66% | -1,335.93 |
| 23 | 328 | 46.95% | -981.90 |
| 37 | 346 | 45.09% | -1,201.41 |
| 53 | 349 | 44.99% | -1,226.66 |
| 71 | 336 | 46.13% | -1,140.50 |

Twelve model outcomes, sixty matched-pool controls and five all-eligible
controls: 77 outcomes, zero target-screen passes. All simulated category,
stock, position and planned-risk checks passed. Source hashes still match.
419 tests passed, including eight new null-selection reproducibility,
probability-independence, pre-fill selection and paired-comparison tests;
four existing sklearn deprecation warnings. Frozen prospective model/source
hashes remain unchanged. Full ignored report
`research_runs/predictive_null/results.json` SHA256:
`6785c740ad55bc4e6f568fc4aa9553fa99c96ac3e8d69598bc9dafcf411ebe3c`.

Conclusion: no clear model-ranking advantage demonstrated by this benchmark;
all adequately active model outcomes remain negative after costs. This does
not establish that no predictive edge can exist. Exposed outcomes, fixed
universe, raw split/revision, SIP completeness and unverified live receipt
remain limitations. No orders, deployment, increased risk or model promotion.
The 90% profitable-active-day objective remains unachieved; independent
prospective evidence is still required.

## 2026-10-10 — Automatic after-close forward outcome audit

Added `prospective_audit_runner.py` and the separate read-only workflow
`.github/workflows/predictive-outcome-audit.yml`. Scheduled weekdays at21:30UTC,
after regular NY close plus the16-minute delayed SIP availability margin in
both DST seasons. GitHub timing is not guaranteed. This does NOT modify the
frozen forecast producer, refit/promote its model, change budgets, deploy the
trading engine or place orders.

The runner discovers every producer workflow run since the frozen manifest's
creation, with pagination and duplicate/wrong-workflow rejection. Failed
terminal runs are included, not removed based on results. Nonterminal runs are
recorded separately and prevent a performance screen pass. Existing auditors
verify remote artifact ZIP digests and conservative upload-completion timing,
decrypt dedicated-key inputs, reproduce forecasts and cumulatively evaluate
completed market sessions. Missing forecasts remain missing evidence, not
no-trade wins. Decrypted inputs are NOT uploaded; only discovery/results JSON
reports are retained for90days. Original encrypted evidence retention remains
90days; this is not permanent archival or guaranteed scheduling.

426 tests passed, including seven new discovery, pagination, failed/pending
run inclusion, source-mismatch and validation-only isolation tests; four
existing sklearn deprecation warnings. Frozen source/model hashes unchanged.
Actual local GET audit discovered the two prior validation-only producer runs,
verified their archive digests and found zero completed forward sessions and
zero forecasts. Full local report SHA256:
`595d62ecd4b2d16df7c0469eb309f54784922bf890432d73758a2aa72fc63209`.

Both new workflow routes were executed in GitHub, not merely configured:

- [Environment validation38068235565](https://github.com/dsarsham-cmyk/autotrader/actions/runs/38068235565)
  completed SUCCESS on source01eed0c. Artifact11675722061 ZIP SHA256
  `129f4b8a0263acf5b6636e0b418fc1200d756605852e50499f261b2b040d34b8`;
  report explicitly environment-validation-only, zero forecasts.
- [Read-only full audit38068303906](https://github.com/dsarsham-cmyk/autotrader/actions/runs/38068303906)
  completed SUCCESS. Artifact11675936934 ZIP SHA256
  `85eb2f49fc661739e4a6fded5e03950c3c91f112f27fbb2bd1caaca978b6bbc6`;
  contains only discovery/results JSON. Actual cloud GitHub read permissions
  and prior archive verification worked. Zero completed/verified sessions,
  no pending runs, performance screen FALSE, independent validation FALSE.

Both artifacts were downloaded, remote-digest verified and backed up locally
under ignored `research_runs/prospective_audit_cloud/`. Saturday environment/
empty-period success is NOT prediction success. Earliest eligible frozen
forward session remains2026-10-12. Actual future forecast anchoring, encrypted
input reproduction, completed-market-data retrieval and cumulative profitability
on real forward sessions remain unverified. This workflow automates those
checks; it does not establish90% winning active days or approve real money.

## 2026-10-10 — More selective opening-VWAP entry

Added `entry_anchor_research.py` to distinguish entry policy from model choice.
The original close anchor is compared with min(opening close, first30-minute
HLC3-volume VWAP). Both use the same +0.1% limit multiplier; the VWAP policy
never raises the limit. Only the modeled10:16NY opening can fill; later dips
are NOT retrospectively counted as fills. This is a selective pullback entry,
not a continuous limit-order execution engine or a proven mean-reversion edge.
All21 features are unchanged and known at the delayed opening-context cutoff.

Logistic and boosted models are separately refitted/calibrated on each policy's
OWN past filled candidate pool, then forecast every unknown test candidate
before selection/fills. Same427 exposed test sessions, stop1%, target0.4%,
60-minute cap, costs10bps per side, stock/category1%/5%, at most3positions and
planned trade risk0.05%. No increase of limits or permission for broker orders.
Original reward-study inputs/source hashes checked; all eighteen close-policy
outcomes reproduced their original exact trades, daily ledger and net profit.

Primary cost10bps / entry delay16minutes:

| Policy | Model | Gate | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|---:|
| Close | Logistic | 0.50 | 314 | 55.73% | -1,044.38 |
| VWAP pullback | Logistic | 0.50 | 269 | 58.74% | -801.86 |
| Close | Logistic | 0.65 | 216 | 60.65% | -729.87 |
| VWAP pullback | Logistic | 0.65 | 181 | 62.43% | -506.61 |
| Close | Boosted | 0.50 | 305 | 55.41% | -1,045.08 |
| VWAP pullback | Boosted | 0.50 | 275 | 57.82% | -790.45 |
| Close | Boosted | 0.65 | 149 | 60.40% | -453.25 |
| VWAP pullback | Boosted | 0.65 | 114 | 57.02% | -405.89 |

At0.90 VWAP/logistic three active days were ALL losing, net-31.99USD;
VWAP/boosted abstained. Close/logistic's two previously exposed wins/+3.59USD
remain too few, not independent evidence. Four cases x3gates x3cost/latency
variants =36outcomes, zero target-screen passes. All simulated risk checks pass.

Fewer trades and changed fill distribution explain some reduced dollar losses;
the comparison does not establish improved expectancy. Fixed-trade zero-cost
accounting at0.50 gives VWAP/logistic gross-9.24USD,62.45% winning active days;
VWAP/boosted gross+36.02USD,64.00%. At0.65 both remain gross-negative
(-27.55/-88.90USD). These are accounting diagnostics with fills/quantity held
fixed, NOT zero-cost deployable strategies or evidence that cheaper fees solve
the accuracy requirement. Cost assumptions are not verified broker commissions.

Seven new tests cover post-cutoff isolation, limit conservatism, absence of
future-dip fills, budget caps, invalid-policy rejection and separate past fill
pool refitting through both model routes while retaining unfilled test forecasts.
Full ignored report `research_runs/entry_anchor/results.json` SHA256:
`1f5a98b263872e65ae711f8003b4413607b1edc764246122dd3cd54c42bfa581`.
Evaluated dependency hashes match. No promotion, deployment or production
settings change; frozen prospective source/model unchanged. Exposed data,
fixed current universe, corporate actions/raw revisions, full-SIP-session
exclusions and OHLC/guard assumptions remain limitations. The stricter entry
is rejected as a sufficient solution: adequately active outcomes still lose
after costs and do not approach90% winning days. Objective remains unachieved.

## 2026-10-10 — Quantified future-completeness conditioning

Added `causal_opening_inventory.py`, an isolated past-only SIP opening-feature
builder and input-universe audit. This corrects candidate membership in the
NEW research input path; it does not rewrite old studies or the frozen forward
producer. Original `active_stock_research.load_universe` calls `sessions`, which
requires all390 minutes before exposing a stock/day to predictive features.
That outcome-availability condition is not known at the opening signal cutoff.
Previously reported historical results already explicitly warned of this bias;
it has now been quantified from actual source caches, not synthetic examples.

The replacement uses exact first30 bars plus prior observed terminal closes
at15:55-or-later. Today's later close is appended AFTER today's features, never
used to qualify its current opening. Cross-sectional mean/breadth includes all
opening-eligible stocks, independently of later outcome completeness. Sixteen
features are built (not an exact21-feature ablation); source SIP/raw cache
metadata and byte hashes are verified before loading. No fill or closing price
is synthesized, and missing outcomes are unknown, not no-trade wins.

Actual inventory2024-02-01 through2026-10-01 (includes training/development
dates, NOT669 independent outer-test sessions):

- 13,355 opening-eligible stock/day rows across669 observed dates.
- 502 rows have usable opening information but fail the original390-bar filter.
- Removing these changes cross-sectional mean/breadth on346 dates, all changes
  material above1e-12; not floating-point-only differences.
- Most affected symbols: NFLX308 rows, AVGO86; remainder108 across18symbols.
- 407 of502 excluded rows nevertheless have every minute of the fixed modeled
  entry46/47 through horizon106/107 window. The missing bars are elsewhere.
- 95 rows also lack at least one required minute in that fixed window.

The retrospective window-coverage check is OUTCOME metadata only; it does not
choose current candidates. Coverage alone is not authenticated execution or
a sparse-bar portfolio simulator. No P&L, model predictions, retraining or
whole-period performance screen was produced by this inventory. Correcting
this bias may improve OR worsen results; it does not explain actual production
losses or establish an economic edge. Next research replay must forecast all
opening candidates before examining outcome availability, and treat selected
unknown outcomes as incomplete evidence, not silently drop or substitute them.

440 tests passed, including seven new current/future-close isolation,
cross-section independence, incomplete-opening rejection, past-history timing,
required-history and outcome-window metadata tests; four existing sklearn
deprecation warnings. Frozen prospective source/model hashes unchanged.
Ignored complete report `research_runs/causal_opening_inventory/results.json`
SHA256 `81ccaca86a9a02d31e63d0d49f4a0d1ca584e0b5329ba10504b9e894c2cf7dcb`.
Evaluated dependency hashes matched. Whole missing dates still require a
separate exchange calendar; fixed-current-universe selection, raw corporate
actions/revisions and unverified original delivery remain limitations. No
orders, deployment, model promotion, real money or increased limits. The
90% profitable-active-day objective remains unmet; this is a concrete
correction to the research method, not a claimed profitable formula.

## 2026-10-10 — Causal opening forecasts with timestamp-indexed outcomes

Added `causal_sparse_research.py` and `causal_sparse_simulator.py`. The new
16-feature opening universe is forecast without conditioning test membership
on future390-bar completeness. Logistic/boosted models fit/calibrate only
known PAST filled outcomes, using240-date warmup,60-date calibration and20-date
outer blocks. Test candidates are all forecast before checking their outcomes.
Same stop1%, target0.4%,60-minute horizon,10bps each side, delayed SIP entry
minute46, stock/category1%/5%, at most3positions and planned trade risk0.05%.

Timestamp-indexed observed bars replace the requirement for an entire390-bar
session. Known unfilled entries do not need later prices; a known stop/target
exit does not require post-exit bars. Missing prices before a required exit
remain UNKNOWN, never filled by interpolation, price padding or future-dip
assumptions. Selection is before fills; an unknown selected outcome stops
the entire cumulative ledger and makes full-period net/win-rate unavailable.
Later days cannot restart equity or substitute another stock. Availability
lists after such a gap are only model ranking before risk sizing, not claimed
actual orders. Known-prefix accounting is explicitly separate.

Actual22 outer folds,8,562 forecasts PER model,429 observed test sessions,
2025-01-16 through2026-10-01. This is a replacement feature/history policy,
not a matched causal-only ablation of previous21-feature results. The date
count differs because current eligibility no longer requires future complete
sessions and prior terminal observations are independently retained.

Primary costs10bps / entry delay16:

| Model | Gate | Active days | Winning active days | Net USD |
|---|---:|---:|---:|---:|
| Logistic | 0.50 | 319 | 55.49% | -1,129.16 |
| Logistic | 0.65 | 223 | 61.88% | -668.34 |
| Logistic | 0.90 | 4 | 75.00% | -5.90 |
| Boosted | 0.50 | 321 | 52.02% | -1,157.31 |
| Boosted | 0.65 | 180 | 57.78% | -557.38 |
| Boosted | 0.90 | 0 | not applicable | 0.00 |

Two models x3gates x3cost/latency variants =18 outcomes, zero target-screen
passes. Selected outcomes happened to be fully recoverable in ALL eighteen
observed-span runs; no unknown selected dates or stopped ledger in this actual
study. This is not a guarantee for future missing data, nor proof of complete
exchange-calendar coverage. All simulated stock/category/position/planned-risk
checks passed. Known-prefix metrics therefore cover the observed span here.

Fixed-trade zero-cost diagnostics at0.65: logistic gross+5.24USD/64.57% wins;
boosted gross-40.49USD/60.00%. Zero-cost accounting freezes fills and quantities,
is not a deployable replay, and still does not approach90% winning days. Costs
are modeled assumptions, not verified commissions. No adequate active variant
is profitable after modeled costs.

452 tests passed, including twelve new exact complete-data path/portfolio
reproduction, irrelevant-post-exit absence, unknown-required-price handling,
known unfilled entry, stop-first gap loss, no substitution/capital restart,
unselected-unknown isolation, loss-guard/gap overshoot, invalid observed bar
rejection and both-model past-only fit/future-unknown forecast tests. Four
existing sklearn deprecation warnings. Frozen prospective model/source hashes
remain unchanged. Full ignored report `research_runs/causal_sparse/results.json`
SHA256 `6ed179baa6ce9692268fde0439711d35284d7233a68fee3ee976251f93c243df`.
Evaluated dependency hashes matched. No orders, deployment, model promotion,
real money or increased risk. Historical outcomes remain exposed; fixed current
universe, raw splits/revisions, missing whole calendar days, original receipt
timing and OHLC/end-of-day-peak assumptions still limit inference. Correcting
future-completeness conditioning did not suffice to produce an economic edge.
Independent forward evidence and the90% objective remain unachieved.

## 2026-10-10 — Headline-event input collection IN PROGRESS

Shifted input research beyond another price-only classifier sweep. Added
`news_research_cache.py`, `news_event_features.py` and the matched comparison
runner `news_predictive_research.py`. Actual authenticated historical-news GET
returned HTTP200 using existing account access; no plan purchase or orders.
The official [news API](https://docs.alpaca.markets/us/reference/news-3) documents
date/symbol queries, pagination,50-item maximum pages, ordering by update date
and rate limiting. Observed account response rate limit200/minute; this private
downloader uses two workers with a shared maximum120requests/minute plus bounded
retry. This observed access is not a universal entitlement/pricing guarantee.

Fixed20-stock query,2024-01-01 through2026-10-02,34 monthly/bounded intervals,
headline responses with include_content=false. Raw provider pages and receipt
metadata are PRIVATE under ignored `cache/news_context`, with immutable byte
hashes and exact request parameters. Identical existing pages are reused;
changed pages, missing receipts, repeated pagination tokens, partial interval
coverage or contradictory article revisions fail closed. This is not original
delivery evidence, and raw provider texts are not published to the dashboard.

Collection is currently RUNNING, not a completed dataset or strategy result.
The executed comparison and complete dataset digests will be reported only
after complete archive verification; a partial archive is rejected by the
loader. The prepared comparison holds the causal stock/date universe and
trading limits fixed, replays price-only results exactly against the preceding
reference, and adds eleven headline-event inputs to the same two classifiers.
No stock is removed because it has no retained news. No threshold/seed choice
is made retrospectively.

Headline inputs count retained versions over24hours and the last hour, with
fixed earnings/guidance/deal/payout/regulatory/analyst and positive/negative
token proxies plus multi-symbol ambiguity. These are crude fixed rules, NOT
FinBERT, a trained language model, authenticated sentiment or a quantum oracle.
The classifier learns their weights only on past training/calibration dates.
The retained text version is assigned at its provider UPDATE time and must be
strictly before10:00NY; it is never backdated to the earlier creation date.
Newly revised future text cannot enter earlier features. Original versions
lost from the provider's latest-version archive are NOT recovered. Resulting
historical omission/revision bias and unverified original receipt remain;
zero news means no retained version in this archive/window, not proof no news
existed. Any subsequent result will be exploratory, not forward validation.

465 tests passed, including thirteen new paginated receipt/reuse/hash checks,
denial/no-fallback, token-cycle/partial/archive-interval/revision rejection,
future article/revision isolation, exclusive cutoff,24-hour window, DST and
no-news stock retention tests; four existing sklearn deprecation warnings.
The comparison runner compiles but its economic results are NOT yet executed.
Frozen prospective model/source hashes still match. No deployment, strategy
promotion, real money or risk-limit changes. Objective remains unachieved.

## 2026-10-10 — Headline-event archive and matched comparison COMPLETED

The preceding in-progress entry is a historical progress snapshot, superseded
by actual terminal execution here. Download finished normally, all34 fixed
intervals complete:1,280 pages /63,205 article rows /63,205 unique IDs. All page
byte hashes matched the completed private archive manifest; article indexing
passed creation/revision timestamp and symbol validation. No contradictory
duplicate revision was selected. Manifest SHA256:
`8392dfe49a09572132b0ca88cf63d454be63e70fc283add37fba04740e7d0d34`.
Raw texts/pages/receipts remain private in ignored `cache/news_context`.

Executed `news_predictive_research.py`, not just compilation. Same13,355 causal
opening stock/day rows;11,685 have at least one retained version in the past
24-hour feature window. No-news rows retain their original candidate membership
and receive zeros, not exclusion. Two matched feature sets:16 causal price
inputs versus the same16 plus11 fixed headline-event proxies. Two classifiers,
22 outer folds /429 observed test sessions each, same costs/budgets/exits.
All eighteen price-only outcomes reproduce the preceding exact daily ledgers,
trades, net results and missing-selection lists.

Primary cost10bps each side / entry delay16minutes:

| Features | Model | Gate | Active days | Winning active days | Net USD |
|---|---|---:|---:|---:|---:|
| Price | Logistic | 0.50 | 319 | 55.49% | -1,129.16 |
| Price + headline events | Logistic | 0.50 | 324 | 56.17% | -1,058.49 |
| Price | Logistic | 0.65 | 223 | 61.88% | -668.34 |
| Price + headline events | Logistic | 0.65 | 219 | 60.73% | -647.47 |
| Price | Boosted | 0.50 | 321 | 52.02% | -1,157.31 |
| Price + headline events | Boosted | 0.50 | 331 | 51.06% | -1,271.54 |
| Price | Boosted | 0.65 | 180 | 57.78% | -557.38 |
| Price + headline events | Boosted | 0.65 | 179 | 55.31% | -697.09 |

At0.90 news/logistic had two active days,50% wins/-9.42USD; news/boosted
abstained. Four cases x3gates x3cost/latency variants =36 outcomes, zero target
screen passes. Selected outcomes were recoverable in all observed-span runs;
no unknown selected date. All simulated stock/category/position/planned-risk
checks passed. This observed coverage is not complete independent calendar or
execution evidence. At0.50 fixed-trade zero-cost accounting gives news/logistic
gross+45.09USD/61.73% wins, news/boosted gross-181.24USD/57.10%. At0.65 both
are gross-negative (-4.00/-167.87USD). Those are frozen-fill accounting
diagnostics, not zero-cost deployable replay or a90% profitable-day result.

465 tests passed again; four existing sklearn deprecation warnings. Frozen
prospective source/model still match. Full ignored economic report
`research_runs/news_ablation/results.json` SHA256:
`12dc00a039e011c9cff52de6347c1cfffbb0af0f969de78fb5b5ce9c1f4a67a5`.
Evaluated source/input hashes matched; complete archive provenance is retained.
No orders, deployment, new subscription, model promotion or increased limits.

Conclusion: these crude event/token inputs do not supply a sufficient economic
advantage. Slight point improvements in one arm are not evidence of statistical
significance; lower dollar loss is not profitability or guaranteed better
expectancy. This does NOT prove all news NLP is useless. It also does not recover
original text versions or authenticate historical delivery: omission/revision
bias remains, as do exposed outcomes, current-universe, corporate-action and
OHLC assumptions. New historical inputs do not turn exposed outcome dates into
independent validation. Objective remains unachieved; no variant is promoted.

## 2026-10-10 — Pretrained financial-language input INFERENCE IN PROGRESS

Added `finbert_headline_inference.py`, `finbert_news_features.py` and
`finbert_predictive_research.py`. This is a new representation of the same
headlines, not another claim that crude token counts are full NLP. The official
[ProsusAI FinBERT card](https://huggingface.co/ProsusAI/finbert) describes
financial sentiment classification with positive/negative/neutral softmax
outputs and Financial PhraseBank fine-tuning; these are NOT probabilities of
future stock returns or profitable trading days. The
[authors' repository](https://github.com/ProsusAI/finBERT) identifies the code's
Apache2.0 license. Model files remain private; no paid inference is used.

Pinned public checkpoint `4556d13015211d73dccd3fdd39d39232506f3e43`, provider
commit metadata2023-05-23, before the study's2024 starting inputs. Expected
published PyTorch weight SHA256 verified against provider LFS metadata and
actual downloaded bytes:
`e15a7b5738df7f17553399b6d94c6e2ff69c89245d066e8e5d183f5803a554e3`.
Six whitelisted configuration/tokenizer/card/weight files were verified by
Git blob or LFS digests. Actual snapshot receipt SHA256:
`e414a084ca168001d516268fdc3389de8d57cc2913aab56dfb01a29f8c0ebc37`.
No custom remote model code: trust_remote_code=false, local-files-only load,
explicit weights_only=true, CPU float32, evaluation/inference mode, four CPU
threads, fixed32-headline batches and96-token truncation. No market fine-tuning
of FinBERT. The later downstream return classifiers fit on PAST market labels.

Installed a separate runtime at
`C:\Users\Ars7am\AppData\Local\AutoTraderResearch\nlp-env` (Windows app
redirects its actual storage into its package-local cache). The initial long
workspace path failed package installation; the shorter isolated path succeeded
without changing Windows settings. Torch2.13.0+cpu / Transformers4.57.3 /
NumPy2.5.3 / tokenizers0.22.2 / safetensors0.8.0. Original production/research
`.venv` still has no torch package; frozen prospective sources/model match.

Actual live CPU inference started and has written verified-context per-batch
checkpoints:63,205 articles reduce to56,284 distinct exact headline strings.
At the recorded inspection9,632 had completed; this is a RUNNING observation,
not a completed corpus, forecasting score or economic result. Cache loader
rejects partial inference, changed source/archive/model/protocol and missing
headline scores. Reusing identical text does not reuse another article's
timestamp: feature attribution still uses each retained version's UPDATE time.
No future revision is backdated before publication; no-news candidates remain
present, and absent sentiment is not invented as neutral.

Prepared matched comparison: existing27 headline-event/causal-price inputs
versus the same27 plus seven24-hour/last-hour sentiment means and dispersion
inputs. Same stock/date universe, budget/stop/cost/timing rules, two downstream
classifiers and predeclared gates. Original headline reference must reproduce
exactly before an effect is reported. The economic comparison has NOT run yet;
it cannot run until all sentiment scores are complete and provenance-matched.

478 tests passed, including thirteen new sentiment normalization, immutable
checkpoint context, incomplete archive/cache rejection, UTF8 text hashing,
future-revision/cutoff isolation, no-news retention, missing-score failure,
dispersion and exact archive/model/source binding tests. Four existing sklearn
deprecation warnings. The downstream runner compiles. Raw inputs, weights and
scores remain ignored private cache files. No orders, deployment, model
promotion, increased risk or real money. Original-version omissions, provider
receipt timing, attribution/truncation, fixed universe and OHLC assumptions
still prevent independent validation. Objective remains unachieved.

## 2026-10-10 — Actual FinBERT checkpoint reproduction, PARTIAL

The original inference process remains live; it has not been restarted because
of an observation timeout or an incomplete status file. Added
`finbert_checkpoint_audit.py` to independently recalculate predeclared saved
batches from the pinned model and original headline bytes. Fixed batch starts
0,8000,16000,32000,56000 are selected before economic outcome inspection,
not chosen from favorable sentiment/profit results. Model file digests, source
digest, input archive and exact runtime package versions must match. Partial
mode reports unavailable batches; full mode requires completed inference and
all five batches. Changed headline membership or scores beyond1e-7 fail closed.

Executed the checker in the isolated NLP runtime, terminal exit0. Three actual
available batches (0,8000,16000),96 headlines, reproduced EXACTLY: maximum
absolute difference0.0 in each. Batches32000/56000 were not yet available.
Report status `partial_fixed_batch_reproduction`, all_fixed_batches_checked=false,
entire_corpus_outputs_reproduced=false, economic_validation=false,
independent_validation_pass=false. This is not proof of every score, authentic
historical news delivery, future return prediction or profitability.
Ignored report `research_runs/finbert_checkpoint_audit/results.json` SHA256:
`0ce5c4deca9522084e34d149bf47d78166bfae435aa9ea279b65860fff79e113`.

483 tests passed, including five new fixed-offset, exact/tolerance, altered
normalized score, missing membership and nonfinite rejection tests. Four
existing sklearn deprecation warnings. Frozen prospective model/source hashes
still match. Economic comparison remains pending until the original full
inference process completes. No orders, deployment, promotion, real money or
risk-limit changes. Objective remains unachieved.

## 2026-10-10 — Exchange-calendar coverage checked against broker GET receipt

Executed `research_calendar_audit.py` against completed causal-sparse and
headline-event studies. The broker calendar contains429 sessions from
2025-01-16 through2026-10-01. All18 sparse and36 headline variants contain
all429 ledger dates: no missing dates, non-calendar rows or incompatible
session windows. The three early closes (2025-07-03,2025-11-28,2025-12-24)
remain in the evaluation; the fixed model horizon ends before those closes.
This confirms ledger calendar coverage, NOT prediction quality or profits.
Previously reported negative net results are unchanged.

The receipt is retrospective, not an authenticated original schedule
delivery. Calendar completeness does not authenticate historical stock/news
delivery, fill assumptions or independent validation. Duplicate dates and
incompatible windows fail closed; a missing ledger day is not silently called
a no-trade day. All approval/independent-validation/order flags remain false.
Private calendar receipt SHA256:
`ba9e4c440e0dbe1d8f50851beacd9b65c393f727999c71bf0b54bde797cae61f`.
Private completed report SHA256:
`d97cafd41637cbe0420b1edb10c913d0942ab58c06dcb1b076bdddc157057837`.

488 tests passed, four existing sklearn warnings; frozen prospective sources
and model still match. Original FinBERT inference process remains running;
at the actual observation35,232 of56,284 distinct headlines had completed.
No full inference/economic result is claimed yet. No orders, deployment,
promotion, risk increase or real money. Objective remains unachieved.

## 2026-10-10 — Prepared matched economic reconciliation before inference ends

Added `finbert_comparison_audit.py`: requires all four predeclared cases and
nine timing/cost/gate variants each (18 matched pairs), rejecting duplicates
or missing variants. Reconciles actual trade P&L into daily P&L and cumulative
equity, active-day win rate and target screen. Missing selected outcomes cannot
create full-period profit or a passing screen; no-trade days are not wins.
Checks retained exchange calendar coverage and records input/receipt/source
digests. Historical paired net differences remain exploratory, not evidence
of independent prediction or permission to trade. Reported risk flags are
checked, but this is not independent reproduction of prices or risk sizing.

Actually ran ledger checks over all36 completed headline-study outcomes:
all reconciled, all reported risk checks true. This is existing headline
evidence, NOT the still-pending FinBERT comparison. Nine new tests cover
case/variant completeness, false favorable flags, trade/day and win-rate
disagreement, partial outcomes and no-trade interpretation. Full suite:
497 passed, four existing sklearn warnings. Original FinBERT process still
live at43,232/56,284 headlines. Economic sentiment effect remains unknown;
no deployment, orders, promotion, risk changes or real money.

## 2026-10-10 — FinBERT inference completed; economic comparison now running

Original CPU process terminated successfully (exit0), all56,284 distinct
headlines scored in1517.2 seconds for63,205 retained article versions.
Original research runtime verified completed status, exact protocol/source,
pinned model weight and news-manifest digests, every required headline hash
and valid normalized finite probabilities. Completed private cache SHA256:
`9994ca15115f70f053d79746ec17c7d01dec930527a43b76762d548453cfd7db`.

Full fixed-batch checker then terminated exit0: all five predeclared batches
0,8000,16000,32000,56000,160 headlines total, reproduced with maximum
absolute difference0.0 each. No missing fixed batches. This is a sample
reproduction, not recalculation of every score or independent market/news
receipt authentication. Checker report SHA256:
`442b635a7c83ca2d5004c8d8a6a112713aafd69f878f35f881fb1f3f07f43e1f`.

Started the actual matched economic runner in the original research runtime.
The process is live; no completed economic result exists at this observation.
Same costs/budgets/limits and historical reference reproduction remain
required. News sentiment remains different from profit probability, and the
historical study is not independent forward evidence. No deployment, orders,
promotion, increased risk or real money. Objective remains unachieved.
