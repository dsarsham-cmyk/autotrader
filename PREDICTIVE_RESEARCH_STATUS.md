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

## 2026-10-10 — Completed matched FinBERT economic comparison: no target pass

The actual first economic run terminated exit1 on an unknown selected NFLX
outcome: the accounting helper received full-period net=None. Corrected the
FinBERT runner only to reconcile a COPY using known-prefix net, while keeping
the original full-period net and win rate unknown. Frozen helpers/sources
were not edited. Two actual tests cover an unknown first/later selection and
prove prefix accounting does not overwrite the unknown full result. After
the confirmed terminal failure, reran the study; terminal exit0.

All18 headline reference outcomes reproduced exactly. Four cases36 outcomes
completed;33 have complete429-session ledgers. Three enriched boosted .5
variants encounter selected NFLX data absence on2025-08-13 and stop the
cumulative ledger. Their full-period net/win rate remain None; they are not
reported as complete profits or compared against a full-period reference.
Known prefixes have101 active days and net -416.43/-623.72/-434.09 USD for
(10bps,16min)/(20bps,16min)/(10bps,17min), respectively, NOT full-period net.

Primary10bps/16min results, 100k initial virtual sleeve (not deployed account):

| Model/gate | Headline baseline netUSD | +FinBERT netUSD | +FinBERT active days | +FinBERT win% |
| --- | ---: | ---: | ---: | ---: |
| Logistic .5 | -1058.49 | -1088.86 |323|55.42|
| Logistic .65 | -647.47 | -651.08 |213|61.50|
| Logistic .9 | -9.42 | -9.42 |2|50.00|
| Boosted .5 | -1271.54 | UNKNOWN full period |101 known prefix|UNKNOWN full period|
| Boosted .65 | -697.09 | -698.90 |194|55.15|
| Boosted .9 | 0.00 | 0.00 |0|not applicable|

No complete variant has positive net; no variant passes the target screen.
One delayed boosted .65 matched pair improves net by43.73USD but still loses
713.00USD, with53.19% winning active days; this is not a profitable discovery.
The other complete nontrivial primary comparisons worsen net, despite the
small logistic .65 increase in winning-day percentage. Raising the probability
gate to .9 does not yield90% wins: it yields two losing-net active days or none.

Executed the matched audit, exit0:18 pairs, zero passing screens, all reported
prefix risk checks true. Calendar coverage explicitly incomplete for the
three stopped ledgers; all other33 cover429 sessions. Complete/input/runtime
provenance and trade/day/equity reconciliation remain required. Historical
news versions, original delivery, fixed universe and modeled fills still
prevent independent validation. No model promotion.
Study SHA256:
`105e4f15b5d349e9b549abaada9401116f9e6acdb71aec507ee53d48a860d726`.
Matched audit SHA256:
`6db52711593409fef7109294301ecef4ede56c770901e5844f45fe254f503d3c`.

499 tests passed, four existing sklearn warnings. Frozen prospective model
and sources still match. No deployment, orders, increased risk or real money.
The requested90% winning days with net profit remains unachieved.

## 2026-10-10 — Own-label60/120-minute holding comparison completed

Tested whether the one-hour timeout cuts off profitable price movements.
Added an isolated duration simulator, preserving original producer/research
sources. Same16 causal opening inputs and candidate universe, same .4%
target/1% stop, stock1%/category5% caps, three positions, planned risk .05%,
10/20bps costs and16/17-minute entry delays. Longer holding changes duration
of exposure, not a claim of identical realized risk. Only60/120 minutes were
declared, both ending before13:00 early closes. Logistic/boosted models learn
each duration's OWN past known-fill labels; no model trained for one hour is
silently reused for two hours. Future unknown candidates remain forecast.

Actual runner exited0: four cases36 outcomes,22 folds429 test sessions.
All18 one-hour reference outcomes reproduced exactly, including actual trades
and daily capital. All36 complete/no unknown selected outcomes, all reported
stock/category/positions/planned-risk checks pass, zero target-screen passes.
Actual broker GET calendar audit exited0: all36 cover429 sessions including
all three early closes, without missing/extra dates or incompatible windows.

Primary10bps/16min results, 100k virtual research sleeve:

| Model/gate |60min netUSD|120min netUSD|120min active days|120min win%|
| --- | ---: | ---: | ---: | ---: |
| Logistic .5|-1129.16|-1151.10|325|54.46|
| Logistic .65|-668.34|-866.95|254|58.66|
| Logistic .9|-5.90|0.00|0|not applicable|
| Boosted .5|-1157.31|-1314.55|331|51.66|
| Boosted .65|-557.38|-677.98|194|59.79|
| Boosted .9|0.00|0.00|0|not applicable|

The larger boosted .65 winning-day percentage does NOT make it profitable:
net deteriorates. A .9 classifier gate gives no active two-hour trading days,
not90% winning days. All complete outcomes remain exposed historical evidence;
none is independently validated or approved for production.
Private study SHA256:
`eb4f46fcea36bf65ba64e376f1b630d9e441673c2ef2c9553ac0c416b99dca39`.
Private calendar audit SHA256:
`0ad39e1a2e63edb2b72d39c2b1fdb2e007f646750389bebb3b4632ebbd71791b`.

510 tests passed, four existing sklearn warnings. New coverage proves exact
one-hour path/portfolio reproduction at both timing/cost assumptions, later
target attribution, missing second-hour data failure, unchanged stop/budgets,
no need for later bars after an early exit/unfilled entry, own past labels and
future unknown retention, and actual-close calendar handling for two hours.
Frozen prospective model/sources still match. No deployment, orders, promotion,
increased budget/stop distance, real money or false target achievement.

## 2026-10-10 — Prior-correlation selection completed, still negative net

Tested whether ranking the top three model probabilities concentrates the
same stock movement. Reused frozen completed causal forecasts WITHOUT
altering probabilities or refitting: greedy descending probability rank,
maximum three stocks; after the first, accept only if every chosen pair has
correlation<=.5 over the prior60 observed session dates, at least40 joint
observations. Returns use each prior observed regular open and last15:55-or-
later close, without cross-day split returns. Missing/constant pair history
does not become zero correlation. Never use the current/future close, selected
future fill or outcome completeness to choose a substitute. No-eligible dates
remain present with unchanged below-gate forecasts.

Executed four cases36 outcomes, terminal exit0. All18 original ranked
reference outcomes reproduced exactly. All36 have complete429-session
ledgers, all reported stock/category/position/planned-risk checks pass, zero
target screens pass. Actual calendar GET audit confirms all429 sessions
including early closes. Inspected7,156 pair-history records: every available
latest date strictly precedes its forecast date; missing pairs remain unknown.
The saved selection evidence contains joint counts, chosen/rejected stocks,
correlations and per-pair input digests. This is provenance for this historical
calculation, not authentication of original data delivery or stable future
correlations.

Primary10bps/16min results, virtual100k research sleeve:

| Model/gate | Original rank netUSD | Correlation selection netUSD | Active days | Win% |
| --- | ---: | ---: | ---: | ---: |
| Logistic .5|-1129.16|-1156.57|330|52.73|
| Logistic .65|-668.34|-613.73|213|62.44|
| Logistic .9|-5.90|-5.90|4|75.00|
| Boosted .5|-1157.31|-1195.36|321|51.40|
| Boosted .65|-557.38|-541.03|172|59.30|
| Boosted .9|0.00|0.00|0|not applicable|

Small .65 improvements remain negative net, not a profitable90% discovery.
Gate .9 again yields four small negative-net days or none; they cannot support
the requested winning-day claim. Historical outcomes remain exposed; fixed
universe, raw data/revisions, original receipts and modeled execution limits
remain. No independent validation or production approval.
Study SHA256:
`6941e946035b403853cb98f68a980c05e1f3b81c9d72f93b4068d05644bc853a`.
Calendar audit SHA256:
`7cfad55993c61da1b801ed74285894236b1a3c75b2cc1aecd7700a9dbe42d7d0`.

517 tests passed, four existing sklearn warnings. Seven new tests cover
unchanged probabilities, correlated rejection, current/future return isolation,
missing pair handling, retained no-trade date, baseline reproduction and no
replacement for future missing selected outcomes. Frozen prospective model
and sources still match. No deployment, orders, promotion, increased risk or
real money. The full objective remains unachieved.

## 2026-10-10 — Basket-day prediction on corrected causal input also failed

The daily meta approach already existed; did NOT claim it was new. Its old
complete-session dataset has later-data selection limitations. Added isolated
`causal_daily_gate_research.py` using corrected sparse candidate forecasts.
Original boosted stock .65 control reproduced exactly before deriving labels.
Past meta labels are positive cumulative base-policy DAY net, conditional on
known past activity, not individual trade wins. Current features use opening
inputs and cross-fitted stock scores only; unknown base outcomes cannot enter
training/calibration. All future feature dates remain. Effective eligibility
gating is explicit and preserves original stock_probability/day_probability.

Same fixed prior meta recipe (120-date warmup,30 calibration,20-date future
blocks; logistic/boosted; .65/.9 gates), same budgets/stops/cost variants.
Actual runner exited0: five cases15 outcomes,309 test sessions2025-07-11 to
2026-10-01, all complete, all reported risk checks pass, zero target passes.
Actual broker GET calendar audit confirms every309 session is present across
all15 outcomes. Meta labels refer to base-policy capital; gated capital/share
counts may differ. This remains exposed historical evidence.

Primary10bps/16min,100k virtual sleeve, MATCHED309-session span:

| Day policy |Active days|Win%|NetUSD|
| --- | ---: | ---: | ---: |
| Stock control, no day gate|130|57.69|-343.47|
| Logistic daily gate .65|53|49.06|-210.84|
| Boosted daily gate .65|42|50.00|-108.94|
| Logistic daily gate .9|0|not applicable|0.00|
| Boosted daily gate .9|0|not applicable|0.00|

Lower total losses through fewer active days are NOT improved profitable
prediction: winning-day percentage decreases and net remains negative. High
gates simply abstain, not90% winning days. No complete variant is positive net.
Do not compare these309-session net totals with earlier429-session totals as
if they were matched periods. No production promotion or independent pass.
Study SHA256:
`bfda37698a61d5232e8aa78743a5720fa7a4cfb86048e5f099068879b036921c`.
Calendar audit SHA256:
`0b2eca5701b491d6cebea83a5eabb8ad328ecc81109276aa1865c330130ffab7`.

521 tests passed, four existing sklearn warnings. Four new tests verify
unknown outcome retention/exclusion from training, day-feature independence
from labels, all test dates kept with explicit original probabilities, and
known no-trade days not winning labels. Frozen prospective sources/model
still match. No deployment, orders, promotion, increased risk or real money.
The full requested objective remains unachieved.

## 2026-10-10 — Trainable circuit first run archived, structural issue found

Implemented four-qubit, two-layer differentiable CPU statevector simulation,
bounded past-only PCA4 inputs, repeated RY data encoding, trainable RY/RZ,
CZ ring, four local-Z expectation readouts and a classical linear head.
Inspired by the parameterized-circuit method described in
[IBM Quantum Learning](https://quantum.cloud.ibm.com/learning/en/courses/quantum-machine-learning/qvc-qnn).
This does NOT imply stock predictability or quantum computational advantage.
Same600 bounded past train/calibration rows for projected logistic control
and circuit,80 fixed training epochs, own past filled outcomes/calibration.
Torch remains isolated; additional pinned research dependencies were installed
there, not in production. Initial import failed on missing cryptography;
installed matching50.0.1 in the isolated environment, then actual run exit0.

Found during actual gradient audit that terminal RZ phases commute with the
chosen Z readout: last-layer phase gradients near floating noise (~1.16e-7),
versus earlier phases >=.01088 on the fixed diagnostic fixture. Those terminal
parameters cannot be claimed effective trainable predictive parameters.
Preserve first implementation in Git and private output before correcting
gate ordering; do not retrofit old results as corrected-model evidence.
Original study SHA256:
`0e6bca6857323881c9893021bbe8768047b14b35a3031689f1d7c57249835f86`.
First circuit .65 primary:39 active days,64.10% wins, -27.58USD net;
.5 full result unknown due missing selected data; .9 no active days.
No target achievement or model promotion is claimed from this first run.

Original environment523 tests passed/three Torch tests skipped (no Torch),
four existing sklearn warnings. Actual isolated runtime executed all five
new tests successfully, including state norm, gradients and deterministic
training. Frozen prospective sources/model still match; no orders/deploy,
real money or budget/stop changes. Next action: structural gate-order fix,
explicit terminal-phase sensitivity test, separately named full rerun.

## 2026-10-10 — Corrected trainable quantum circuit completed, no profitable pass

Archived first implementation in commit eb3f989. Corrected each learned
phase to precede a noncommuting learned RY rotation rather than end next to
the Z readout. Actual terminal-phase sensitivity test now shows all four
last-layer phase gradients >.001 on the fixed fixture. Isolated runtime
executed all six tests successfully. Deterministic training, state norms,
finite gradients, unchanged past preprocessing under altered future input,
and preserved predictions for existing test rows remain verified.

Separately named `research_runs/variational_quantum_corrected/results.json`
completed, actual exit0,22 folds per model,18 outcomes. Classical projected
control reproduced the initial run EXACTLY. All22 circuit weight-artifact
digests changed after gate correction; all22 training losses decreased.
This verifies effective optimization, NOT convergence/global optimality or
future predictive profit.80-epoch budget remains explicitly not certified
converged. Past-only scaler/PCA,600-row bounds, calibration and same market
source/forecasts limits are recorded along with per-fold weights/losses.

Primary10bps/16min,100k virtual sleeve:

| Model/gate |Active days|Win%|Full netUSD|
| --- | ---: | ---: | ---: |
| Projected logistic .5|326|54.29|-1166.58|
| Projected logistic .65|205|55.12|-739.45|
| Projected logistic .9|0|not applicable|0.00|
| Corrected circuit .5|101 known prefix|UNKNOWN|UNKNOWN|
| Corrected circuit .65|39|64.10|-27.58|
| Corrected circuit .9|0|not applicable|0.00|

All18 target screens false,16 complete ledgers, two circuit .5/10bps ledgers
(16/17min) stop on selected unknown NFLX history. Primary first unknown is
2025-08-26. No favorable replacement, capital restart or omitted unknown day.
All reported prefix budget/risk checks pass. Actual broker-calendar audit
records429 expected sessions, coverage complete for16 outcomes and incomplete
for two stopped ledgers. No complete variant has positive net. Fewer losing
trades, sparse39-day observations or a .9 classifier gate cannot certify90%
winning days. Historical outcomes remain exposed; this is not independent
validation or evidence against all possible trainable circuit designs.
Corrected study SHA256:
`f5a0dca9152b0d90b0560d6b7730d94f20259539e1895d7a35beec16cb632145`.
Calendar audit SHA256:
`3d3f137b17dfc596324684d66ef2e0a6caae0cacb7e73b073180aebfff68d877`.

Original environment523 tests passed/four Torch-only tests skipped, four
existing sklearn warnings; all six dedicated classifier tests actually pass
in the isolated Torch runtime. Production still has no Torch; frozen sources
and model match. No quantum hardware/fees, orders, deployment, model promotion,
increased risk or real money. Full objective remains unachieved.

## 2026-10-10 — Quantum training stabilized; economic objective still fails

Added `quantum_training_plateau.py` and isolated runner. Same corrected
circuit, parameters, seed, past600-row scaling/PCA/training/calibration and
optimizer; reproduce each saved80-epoch weight artifact EXACTLY before
continuing. Stop only from PAST TRAINING loss: minimum160 epochs, last64
loss values range<=1e-5, hard cap512. Test/calibration values do not decide
stopping. A training-loss plateau is NOT proof of global convergence, a
global optimum, forecast calibration or profitable prediction.

Actual isolated tests3 passed, including exact80-epoch trajectory, future
input invariance of training/stopping and incompatible checkpoint rejection.
Actual full runner exit0: all22 original80-epoch weight artifacts reproduce,
all22 training fits meet the declared plateau criterion in160–214 epochs,
none needs the cap. Same429 test-date span; no retraining on future outcomes.

Primary10bps/16min,100k virtual sleeve:

| Gate |80epoch control active/win%/netUSD|Stabilized active/win%/netUSD|
| --- | --- | --- |
| .5 |101 known-prefix / UNKNOWN / UNKNOWN|100 known-prefix / UNKNOWN / UNKNOWN|
| .65 |39 /64.10 /-27.58|39 /66.67 /-20.29|
| .9 |0 /not applicable /0.00|0 /not applicable /0.00|

Matched improvement .65 is7.28USD, still negative,39 active observations,
not90% winning days. One-minute latency stress .65 has61.54% wins and
-66.43USD net;20bps stress .65 has0% wins and-88.94USD. No complete variant
has positive net. Across nine reference plus nine new variants:14 complete
ledgers, four unknown-full-result ledgers, zero target-screen passes, all
reported prefix risk checks true. New .5/10bps variants first lack selected
NFLX outcome2025-08-26 and stop the ledger, never restart capital or substitute
a favorable known stock. Broker GET calendar audit expects429 sessions,
confirms14 complete spans and marks four stopped spans incomplete.

Study SHA256:
`fc770787831a199035060e32b9d0d9e9f9bc91b291bc163c6f3f1df8fbeecc35`.
Calendar audit SHA256:
`eddf7c310883964025e9819369450ab9453d075a0bcefcf62eea24db4b1c12fd`.
Original environment524 tests passed/six Torch tests skipped, four existing
sklearn warnings; the three new Torch tests actually execute successfully in
the isolated runtime (the skipped count is not presented as passed tests).
Frozen prospective sources/model still match. No orders, deployment, model
promotion, increased risk, quantum hardware fees or real money. Full objective
remains unachieved; successful training is not successful trading.

## 2026-10-10 — Next-minute profit protection comparison completed

Added isolated profit-lock path and unchanged original cash/risk bookkeeping.
Preserved initial1% stop, .4% target, stock1%/category5% budgets, three positions
and planned-risk .05%. A completed minute with high>=entry raw+.3% and close
above the proposed stop plus one cent may request a tighter cost-adjusted stop
for NEXT minute. Proposed stop yields+.02% net at exact modeled stop fill;
never activates at/above the profit target or lowers original protection.
Same-bar low cannot retroactively execute a new stop. Gap execution uses the
less favorable actual open, so profit is not guaranteed. Source distinction:
[Alpaca order documentation](https://docs.alpaca.markets/us/docs/orders-at-alpaca)
also describes stop-triggered market execution as potentially different from
the stop price. This simulated amended fixed stop is NOT a confirmed broker
trailing/bracket replacement implementation; none has been deployed.

Logistic/boosted models train on each policy's OWN known past fill labels;
future unknowns remain candidates. Actual runner exit0: all18 fixed-stop
reference outcomes reproduce exact trades/daily/net. Four cases36 outcomes,
all complete429-session ledgers, all reported prefix risk checks pass, zero
target-screen passes. Actual GET calendar audit confirms all429 sessions for
all36 variants, including early closes.

Primary10bps/16min,100k virtual sleeve:

| Model/gate |Fixed netUSD|Profit-lock netUSD|Lock active days|Lock win%|Lock exits|
| --- | ---: | ---: | ---: | ---: | ---: |
| Logistic .5|-1129.16|-1083.28|318|61.01|144|
| Logistic .65|-668.34|-870.54|257|61.87|112|
| Logistic .9|-5.90|-3.36|6|83.33|2|
| Boosted .5|-1157.31|-1178.19|319|55.49|140|
| Boosted .65|-557.38|-940.28|237|57.38|96|
| Boosted .9|0.00|0.00|0|not applicable|0|

One .9/logistic/10bps/17min variant has positive0.18USD net on SIX active
days. This tiny exposed sample is not validation of profitability or90%
winning days, and is NOT promoted. Substantially active variants remain net
negative. Changing exit protection also changes labels/selection, so this is
not a same-trade counterfactual ablation. No widening stops or leverage.
Study SHA256:
`690e31130d6ae665e5f3bf5306792fbfd941f8c823221f47c6ec4f785053f14e`.
Calendar audit SHA256:
`359ee1a91751af569ad94938bb45ec4be9595f320daf3ca84d02359256bcd1bd`.

533 original-runtime tests passed/six Torch tests skipped, four existing sklearn
warnings. Nine new tests cover exact disabled-policy reproduction, next-minute
activation, same-bar initial-stop priority, gaps below profit lock, invalid
request close/infeasible cost, missing next minute, unchanged planned-risk
sizing/caps and own past labels/future unknown retention. An initial fixture
incorrectly allowed a valid later activation; narrowed fixture to isolate the
intended bad-close case, without changing strategy or historical inputs.
Frozen prospective sources/model still match. No orders, deployment, model
promotion, increased risk or real money. Full objective remains unachieved.

## 2026-10-10 — Same-forecast exit ablation reveals trimmed-winner cost

Previous profit-lock test retrained own labels, changing selections as well
as exits. Added `fixed_forecast_profit_lock.py`: freeze the original causal
probabilities/candidate proposals, compare fixed versus protected exits, use
own evolving capital and unchanged caps for the risk replay. Original18
control outcomes reproduce exact trades/daily/net. Separate fixed-entry/qty
diagnostic isolates exit mechanics but is explicitly risk_approved=false:
unchanged reference quantities can violate caps on changed capital. It is
NOT sold as an executable policy. Aggregate account-guard contexts are marked
unavailable for individual-path diagnostics; unknown counterfactual prices
remain unknown, no zero fill or omitted loss.

Actual runner exited0, four cases36 variants, all complete429-session ledgers,
all reported stock/category/position/planned-risk checks pass, zero positive
net outcomes and zero passing target screens. Actual broker-calendar GET
confirms all429 expected sessions for all36 variants.

Primary10bps/16min,100k virtual sleeve, same proposals:

| Model/gate |Original netUSD|Protected replay netUSD|Active days|Protected win%|
| --- | ---: | ---: | ---: | ---: |
| Logistic .5|-1129.16|-1167.92|319|58.93|
| Logistic .65|-668.34|-687.03|223|65.02|
| Logistic .9|-5.90|-7.66|4|75.00|
| Boosted .5|-1157.31|-1203.13|321|55.45|
| Boosted .65|-557.38|-583.95|180|61.11|
| Boosted .9|0.00|0.00|0|not applicable|

Actual same-quantity logistic .65 diagnostic over380 paired trades:
13 original losing/flat trades become wins, but69 winners are trimmed;
total net change-18.68USD. The replay's higher daily win percentage does NOT
make more money. This identifies a concrete exit-payoff tradeoff, not proof
of future behavior. Do not promote an exit simply because it makes more days
green. Same frozen classifier probabilities refer to the original exit labels,
so this is an exit-mechanism study, not a recalibrated predictive model.
Study SHA256:
`65eadd4c816f07e6abe87d1ed6d3f4f2627c3d1f7d89b447d4c1d2fc25d1e020`.
Calendar audit SHA256:
`024e24ea54aa0d7e85828873fb8d055a31065b3fe7f7b9f34b4fd7278d8d8796`.

538 original-runtime tests passed/six Torch tests skipped, four existing
sklearn warnings. Five new tests cover entry/qty preservation without trading
approval, missing counterfactual prices, aggregate guard refusal, changed
entry/net rejection and retained no-trade interpretation. Frozen prospective
model/sources still match. No orders/deploy, strategy promotion, risk increase
or real money. The requested90% winning days AND net profit remain unachieved.

## 2026-10-10 — Actual recent PAPER fill-to-NBBO quote audit, no cost reduction

Existing quote pilot already has72 completed small windows; do not present
this as the first spread check or as representative total execution cost.
Added GET-only `paper_fill_quote_audit.py`: latest20 FILL activities from
paper account, historical SIP quotes in a bounded seed/fill window, latest
quote at/before each activity transaction_time with maximum age2sec. Future
quotes ignored, conflicting/invalid terminal state not replaced by an earlier
favorable quote, stale/missing evidence remains unknown. Raw activity/quote
receipts are private ignored files, exact input/source hashes in report.
No broker order/replace/cancel request or subscription change.

Actual run exited0: all20 recent fills matched, no missing quote evidence.
They are concentrated in ONE eight-second EOD closing batch:
2026-10-09T19:55:23.408569Z to19:55:31.35602Z. This is not an entry/exit,
all-session, all-market or independent representative sample. Largest quote
age0.400817sec.16 fills fall within/at the last displayed spread, four outside;
this does not prove a fill bug because paper transaction timing versus quote
changes/original delivery remains unauthenticated.

Median full quoted spread0.655024bps. Median signed fill deviation from
contemporaneous quote midpoint0.424681bps (range .096902–1.846226bps).
These are NOT broker fees, decision-to-fill latency, market impact, queue
costs or actual real-money execution cost. Therefore research10/20bps cost
assumptions remain unchanged, cost_assumptions_changed=false. Primary source:
[Alpaca paper-trading documentation](https://docs.alpaca.markets/us/docs/paper-trading)
states simulated fills do not account for market impact, latency slippage,
queue position and regulatory fees. Paper sample cannot certify live costs
or make an exposed historical strategy independently validated/profitable.

Private completed report SHA256:
`d0c3a8290307eeb20d958ff531ead32e03e0d7928088d70f8e9a7d19f275f32d`.
Activity receipt SHA256:
`a2ae4fdfe964f067b847cc0cc8663deab862792dd4ca69bccc8e2fbc417eb3ef`.
544 original-runtime tests passed/six Torch tests skipped, four existing
sklearn warnings. Six new tests cover future quote isolation, invalid/conflict
terminal state, stale/missing evidence, side-adjusted sign, duplicate/order
rejection, invalid fill and explicit timezone. Frozen prospective model/sources
still match. No orders, deployment, model promotion, risk/cost relaxation or
real money. Requested90% profitable winning days remain unachieved.

## 2026-10-10 — Past-frequency predictive/economic baselines completed

Added `past_frequency_predictor.py` and `past_frequency_research.py`. Fixed
baselines use ONLY known-filled outcomes in each prior60-session calibration
window: global frequency with Laplace smoothing, and stock frequency shrunk
toward that past global rate using predeclared20-row mass. No price features,
future-derived vocabulary, test labels, future counts or tuning of mass/gates.
Shrinkage is an empirical frequency rule, not certified Bayesian uncertainty.
Unknown/unfilled past labels are not inserted as losing/winning observations.
Same future candidates, chronological22 folds and portfolio risk/cost rules.
Equal-probability selection retains the original alphabetical tie convention.

Actual runner exited0. Both new18 baseline outcomes have complete429-session
ledgers, zero positive-net variants and zero target-screen passes. Existing
54 model outcomes are imported unchanged and ledger-reconciled, NOT newly
executed/retrained by this baseline runner. Combined72 outcomes:70 complete,
two existing unknown full-result ledgers (stock-interaction logistic .5/10bps
missing selected NFLX2025-06-26); overall calendar coverageFALSE. Actual GET
calendar confirms429 expected sessions and recognizes incomplete spans.
All reported prefix risk checks pass, not independent fill/risk reproduction.

Primary10bps per side, delay16:

| Baseline/gate | Active days | Winning percent | Net USD |
|---|---:|---:|---:|
| Recent global .5 |286|44.06|-918.80|
| Recent global .65 |0|not applicable|0.00|
| Recent global .9 |0|not applicable|0.00|
| Shrunk stock .5 |322|52.17|-1223.21|
| Shrunk stock .65 |188|60.11|-574.35|
| Shrunk stock .9 |0|not applicable|0.00|

Exact same4161 known-filled test keys and recomputed model Brier scores were
verified before comparison; test outcome membership is scoring-only, not
forecast/selection filtering. Global baseline Brier.251226, shrunk stock.248214.
Price-only logistic.242525 and boosted.243595 both improve descriptive error
relative to either simple baseline. All six models beat global baseline;
five beat shrunk stock, interaction logistic.248294 does not. The12 paired
comparisons reuse the SAME observations, not12 independent discoveries.
No significance, independence or profitability is inferred from these small
descriptive score differences. Probability-score improvement does not ensure
positive payoff after loss severity/costs; the joint90%/profit goal remains unmet.

Study SHA256:
`72023a14328dabb6d32fa6c6f940048907712ded572d862e6fa913ab65a86e27`.
Calendar audit SHA256:
`7d4ff3d2d7b36f28448903cabd125eedf2d57471dd1077b7cd0759618f23f247`.
575 tests passed/six Torch skipped/four existing sklearn warnings. Five new
tests cover count/smoothing/shrinkage math, no-history stock fallback,
future label/feature/price/candidate isolation, one-class smoothing and
future/duplicate/missing/unknown evidence rejection. Frozen prospective model/
sources still match. Exposed dates/current universe/revisions/original delivery/
execution assumptions remain limitations. No orders/deployment/promotion,
increased leverage/budgets, reduced costs or real money. Goal remains unachieved.

## 2026-10-10 — Date-effective split input normalization, isolated research

Added `split_context_audit.py` and `split_predictive_research.py`. GET-only
corporate-action endpoint documented at
https://docs.alpaca.markets/us/v1.1/reference/corporateactions-1.
Actual complete response returns four forward splits in the fixed universe:
WMT3:1 on2024-02-26, NVDA10:1 on2024-06-10, AVGO10:1 on2024-07-15 and
NFLX10:1 on2025-11-17. Latest downloaded records are NOT authenticated
historical announcement receipts. No point-in-time delivery claim.

New isolated feature builder rescales accumulated past closing prices divided
by the new/old share ratio and past opening volumes multiplied by that ratio,
only when ex_date is reached. Earlier output features remain unchanged.
Missing effective session applies the unit change before next observed session.
Current raw intraday prices, candidate eligibility, execution labels, budgets,
costs, stop distances and frozen prospective source/model are unchanged.
No-event builder exactly reproduces original causal16-feature inputs.

Actual input audit exited0:13,355 input rows,84 affected rows on84 dates.
Raw apparent gap versus normalized same-unit gap on effective dates:

| Symbol | Raw gap percent | Same-unit gap percent |
|---|---:|---:|
| WMT |-66.324903|+1.025290|
| NVDA |-90.042610|-0.426095|
| AVGO |-90.015698|-0.156978|
| NFLX |-90.045883|-0.458833|

This identifies concrete input distortion, NOT its causal contribution to
production losses or proof that correcting it yields profitable predictions.
The correction exists only in research, not a production bug-fix deployment.
Dividends/spin-offs/mergers, fixed current universe, historical revisions and
unauthenticated original data delivery remain limitations.
Input audit SHA256:
`dbf4219c336460c59e1f84ffaf830b072fd1ade0ec78ccd4d8c3d32fb166089c`.
Corporate-action receipt SHA256:
`d805990261708d3f40e567c23dda5587e31089f020f96267aed72e2c154d94bd`.

554 original-runtime tests passed/six Torch tests skipped, four existing
sklearn warnings. Ten new tests cover exact no-event control, no backdating,
current raw units, future close isolation, missing effective sessions,
reverse-split direction, invalid/conflicting events, all-candidate ordering,
reference reconciliation and unknown full results. No orders or deployment.
Actual matched economic comparison exited0. Both models fitted using only
known past labels and corrected date-effective input features; original18
control outcomes exactly reproduce saved trades/daily/net. All36 outcomes
have complete429-session ledgers; actual GET calendar audit confirms coverage.
All reported stock/category/position/planned-risk checks pass; zero target
screen passes. Reconciliation is not independent reproduction of fills/risks.

Primary corrected results at10bps per side, entry delay16minutes:

| Model/gate | Active days | Winning percent | Net USD |
|---|---:|---:|---:|
| Logistic .5 |324|56.48|-1114.80|
| Logistic .65 |220|60.00|-777.31|
| Logistic .9 |2|100.00|+3.54|
| Boosted .5 |322|51.86|-1226.46|
| Boosted .65 |173|57.80|-627.81|
| Boosted .9 |0|not applicable|0.00|

The100% figure is just TWO exposed active observations, descriptive interval
34.237–100%, not evidence of90% future winning days or profitability. The
one-minute delayed variant also has two wins/+3.54USD, not independent data.
At gates with substantial activity, correcting bad units does not rescue
profitability; .65 logistic worsens from-668.34 to-777.31USD and boosted from
-557.38 to-627.81USD. Cleaner inputs are necessary but not a new predictive edge.
No promising subset is promoted or allowed to reset the exposure history.
Study SHA256:
`15f3cd573ba7312626ac47e0556d699d191b4ceedfd87e0d5114a3efeb827a87`.
Calendar audit SHA256:
`a50a5e21f106e60468e1fd92ce777120c3336eae8c0494b0597214a7c57dd412`.
Frozen prospective source/model still match. No broker orders, deployment,
automatic model promotion, increased limits, cost reduction or real money.
Requested90% profitable winning days remain unmet.

## 2026-10-10 — Completed split-normalized classical/quantum matched study

Added `split_quantum_research.py`; actual isolated CPU run exited0.
Six cases: original raw versus date-effective split input, each with projected
logistic, corrected80-epoch variational circuit and train-only plateau circuit.
Past-only PCA4, bounded600 train/calibration rows, same four-qubit/two-layer
statevector, seed19, calibration and portfolio constraints. No hardware purchase,
quantum advantage claim, production model replacement or risk/cost relaxation.

All27 raw-input control outcomes exactly reproduce original trades/daily/net;
all66 original fold spans, preprocessing and fitted artifacts reproduced.
For each split-normalized plateau fit, its own corrected-input80-epoch artifact
reproduces before continuing; this is NOT the old raw-input model hash.
Both raw and normalized22-fold plateau cases stabilized on training loss alone,
raw160–214 epochs, normalized160–228, no cap reached. This does not certify
global convergence or trading accuracy. Split events never adjust earlier
feature rows. Current raw entry/exit units, labels and eligibility unchanged.

Primary split-normalized outcomes at10bps per side, delay16:

| Model/gate | Active days | Winning percent | Net USD |
|---|---:|---:|---:|
| Projected logistic .5 |320|57.19|-985.80|
| Projected logistic .65 |240|57.92|-786.71|
| Projected logistic .9 |0|not applicable|0.00|
| Quantum80 .5 |60 known-prefix|unknown|unknown|
| Quantum80 .65 |25|48.00|-153.56|
| Quantum80 .9 |0|not applicable|0.00|
| Quantum plateau .5 |61 known-prefix|unknown|unknown|
| Quantum plateau .65 |26|57.69|-132.39|
| Quantum plateau .9 |0|not applicable|0.00|

Raw .65 quantum80 has39 active/64.10%/-27.58USD; plateau39/66.67%/-20.29USD.
Correcting units worsens these economic outcomes, rather than revealing a
profitable hidden quantum model. Fewer active days do not imply better accuracy.

Across54 outcomes:44 complete429-session ledgers, ten unknown full results,
zero positive-net complete variants and zero target-screen passes. All
reported prefix stock/category/position/planned-risk checks pass, not an
independent reproduction of execution/risk behavior. Actual GET calendar audit
marks44 spans interpretable and ten incomplete; overall complete coverage is
FALSE, not silently advertised as54 full-period tests.
Raw .5 quantum80/plateau10bps stop at missing selected NFLX2025-08-26;
normalized .5 quantum80/plateau all cost/delay variants stop at selected
NFLX2025-05-22. Missing outcomes remain unknown, no substitution/reset/removal.

Study SHA256:
`6c067489adf99efdffcbe0f8ff40a6fc4fc9c25f36a6d1d670320249fe92911d`.
Calendar audit SHA256:
`df64283de530ec5ec431643768da692c0c27d7a8b54cc49bccc0bb4633b1dbd3`.
556 original-runtime tests passed/six Torch tests skipped, four existing sklearn
warnings. Eleven quantum/plateau/new-comparison tests actually pass in isolated
Torch runtime. Frozen prospective sources/model still match. All outcome dates
previously exposed, current split announcement delivery unauthenticated,
fixed-universe/revision/receipt/fill limitations remain. No orders, deployment,
automatic promotion, increased risk or real money. Goal remains unachieved.

## 2026-10-10 — Fixed recency-weight hypothesis, first run retained

Added `recency_predictor.py` and `recency_predictive_research.py`. Same
split-normalized16 inputs, expanding past training/separate60-session
calibration/20-session future blocks; fixed60/120-observed-session exponential
half-lives. Mean-one weights separately in train/calibration preserve total
row mass; weighted scaler/classifier/calibrator, no future labels or outcome
filtering of test candidates. Effective row-weight size is NOT an independent
observation count. All54 first-run outcomes complete; all18 unweighted control
outcomes exactly reproduce saved daily/trade/net reference. Zero target-screen
passes, all reported prefix risk checks pass. This is exposed exploration.

First run contains StandardScaler weighted-variance sqrt RuntimeWarnings.
Finite forecasts alone do NOT explain those warnings; numerical audit is
required before relying on this implementation. This first report/source
version is retained, not retroactively edited to hide warnings.
First report SHA256:
`7ff17516de8189235ed4aa376f1b05394fbf8e26e6c5c8423715aeb9bbf2797a`.
562 tests passed/six Torch skipped/four pre-existing sklearn warnings;
six new tests cover past-only weights/half-life/mass, future-label and
future-candidate isolation, overlap/classes and actual weighted scaler mean.
No deployment/orders/real money, no risk/cost relaxation. Goal remains unmet.

## 2026-10-10 — Recency numerical audit and exact economic replay completed

First warning-bearing implementation retained in commit14e9c65 and private
first report. Added fail-closed weighted-scaler audit, without changing fitted
parameters: negative variance is accepted ONLY on an exactly constant column,
within tiny rounding tolerance, with actual unit scale and finite parameters/
transforms. Unexpected fitting warnings or substantive/nonconstant negative
variance fail. Known sqrt warnings captured and classified in fold metadata,
not blanket suppressed. Official weighted-scaler reference:
https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html.

Actual separate audited rerun exited0. All54 outcomes AND forecast rows exactly
reproduce first run.88 weighted fits audited:44 explained sqrt warnings, only
feature9 `opening_coverage`, exactly constant1; most negative stored variance
-1.4699279110654225e-42. sklearn already uses unit scale for that constant column;
no parameter/forecast/economic change. This is numerical correctness evidence,
not a new predictive edge or independent financial validation.

Primary outcomes at gate.65,10bps per side, delay16:

| Model/half-life | Active days | Winning percent | Net USD |
|---|---:|---:|---:|
| Logistic/unweighted |220|60.00|-777.31|
| Logistic/60 |209|61.72|-688.97|
| Logistic/120 |219|62.10|-718.23|
| Boosted/unweighted |173|57.80|-627.81|
| Boosted/60 |186|53.76|-643.79|
| Boosted/120 |203|59.11|-571.94|

Weighted inputs improve some losses, not profitability or90% winning days.
All54 ledgers complete over429 sessions; actual GET calendar audit confirms
coverage. All reported prefix risk checks pass, zero target-screen passes.
High-confidence .9 primary logistic60 has two active/50%/-9.52USD,
logistic120 three active/66.67%/-7.57USD; boosted abstains. Unweighted .9
control's two wins/+3.54USD remains the same sparse nonvalidated artifact,
not evidence for promoting a model. Two weighted delayed17-minute .9 variants
are positive: logistic60 two wins/+3.40USD, descriptive interval34.237–100%;
logistic120 three wins/+5.35USD, interval43.849–100%. These are retained, not
hidden, but2/3 exposed observations and one-minute-sensitive sign changes do
not establish90% profitable future days. Do NOT claim all weighted variants
are negative. All variants retained, no winner selected
from this exposed experiment. Frozen prospective/production state unchanged.

Audited study SHA256:
`8af20f95300b34840c41a6783b0d3b159f24d689589ff677def75682d3113216`.
Calendar audit SHA256:
`16c17c94cab15d19b98ffaadc4cd59f4293e79f750092589cce42402d7eaf014`.
563 tests passed/six Torch tests skipped/four existing sklearn warnings.
Seven new tests now include rejection of real/nonconstant/nonfinite variance
errors and accepting only proven exact-constant tiny rounding without mutation.
No orders, deployment, increased budgets/leverage, cost reduction, automatic
promotion or real money. Full objective remains unachieved.

## 2026-10-10 — Fixed stock-identity/interactions comparison completed

Added pure `stock_identity_features.py` and isolated `stock_identity_research.py`.
Three predeclared arms: corrected price16 only, plus20 fixed stock indicators
(36 inputs), plus each stock's16 price-feature interactions (356 inputs).
Fixed vocabulary from existing20 stocks, not fitted from future membership.
Original input rows/prices unmodified. Same past-only logistic/boosted models,
calibration chronology, costs/delays, stop/target and risk constraints.
This tests stock heterogeneity, not a claim of sector causality or a new
point-in-time universe. Statistical overfitting risk increases with parameters.

Actual run exited0; all18 price-only controls exactly reproduce daily/trades/
net reference.88 new fold fits with no recorded fitting warnings; any unresolved
warning fails the runner rather than claiming a successfully trained model.
54 outcomes,52 complete429-session ledgers, two full results unknown, zero
target-screen passes, all reported prefix risk checks pass. No positive-net
complete NEW identity variant. Positive sparse price-only controls remain
retained as previously disclosed, not attributed to identity features.

Primary10bps per side, delay16, gate.65:

| Model/input | Active days | Winning percent | Net USD |
|---|---:|---:|---:|
| Logistic price-only |220|60.00|-777.31|
| Logistic stock indicators |208|56.73|-762.23|
| Logistic stock interactions |105|56.19|-364.86|
| Boosted price-only |173|57.80|-627.81|
| Boosted stock indicators |170|59.41|-597.89|
| Boosted stock interactions |175|59.43|-637.68|

Interaction logistic loses less while trading much less, not achieving higher
win accuracy. All new .9 primary identity gates abstain except interaction
logistic: one active losing day/-1.23USD. No-trade is not a win.

Descriptive Brier uses the SAME4161 known-filled primary test candidates;
future outcome membership is used ONLY to score, never to select forecasts.
Logistic price-only.242525, indicators.243735, interactions.248294;
boosted price-only.243595, indicators.243967, interactions.243764.
All identity arms have worse Brier than their matched original classifier.
This does not establish significance or independent forecast performance,
but rejects a claim that these identity variants improved measured accuracy.

Interaction logistic .5/10bps delay16/17 stops at selected missing NFLX
2025-06-26. Whole-period net/win remains unknown, not prefix-as-full result.
Actual broker GET calendar audit expects429 sessions;52 spans interpretable,
two incomplete, overall full coverageFALSE. No favorable substitution/reset.
Study SHA256:
`95be17817162365ac7364a047cdc7a60fb340a0c433cff1738114c3a1b4b66d2`.
Calendar audit SHA256:
`bd5a8329c2bd437f1e56cc5aafc52f62f8207e8d02cfd387978dd47db7bc20ad`.
570 tests passed/six Torch skipped/four existing sklearn warnings; seven new
tests cover dimensions/schema, unchanged raw units, nonmutation, fixed symbol
slot and isolated interactions, future-candidate independence and invalid inputs.
Frozen prospective model/sources still match. All historical outcomes already
exposed; survival/revision/original delivery/fill assumptions remain. No orders,
deployment, automatic promotion, increased leverage/budgets, reduced costs or
real money. Requested90% profitable winning days remain unachieved.

## 2026-10-10 — Corrected causal/sparse conditional-payoff study completed

Added `causal_payoff_research.py`, reusing the earlier conditional gain/loss
head recipe, NOT presenting it as the first payoff-model experiment. Previous
study used different21-feature/full-session-filtered inputs; this uses corrected
causal16 price context, date-effective split units and sparse timestamp-indexed
outcomes. All opening candidates retained; only KNOWN PAST fills fit heads.
Expected net return=P(win)*mean(net gain)-(1-P(win))*mean(net loss).
Separate past calibration offsets, same probability forecasters, budgets,
stop/target, timing and10/20bps stress. No future-derived execution substitution.

Actual runner exited0:44 chronological folds across two model families, no
unresolved fitting warnings. Original calibrated probability forecasts exactly
reproduced; all18 probability-only reference outcomes reproduce daily/trades/
net. Six model/selector cases54 outcomes all complete429-session ledgers, zero
target-screen passes, all reported prefix risk checks pass. Actual broker GET
calendar confirms full429-session spans. Not independent fill/risk reproduction.

Primary10bps per side, delay16, true probability gate.65:

| Model/selector | Active days | Winning percent | Net USD |
|---|---:|---:|---:|
| Logistic probability only |220|60.00|-777.31|
| Logistic positive expectancy/probability rank |7|71.43|-13.27|
| Logistic positive expectancy/net rank |7|71.43|-13.27|
| Boosted probability only |173|57.80|-627.81|
| Boosted positive expectancy/probability rank |10|50.00|-27.50|
| Boosted positive expectancy/net rank |10|50.00|-27.50|

Loss reduction is mostly abstention, not demonstrated profitable prediction.
Positive expectancy is a MODEL estimate, not actual economic truth. At.9 the
logistic filters retain the same two original control wins/+3.54USD; delayed
variant the same two days/+3.54USD. These are duplicate sparse observations,
not newly discovered opportunities or evidence for90% future winning days.
The boosted.9 cases abstain. All results retained without model promotion.

Ordinal scores only implement selection ordering: simulator gate.5 is NOT
calibrated probability. Original true gate is `probability_threshold`, actual
forecast preserved in `forecast_probability`. Calendar audit now records true
gate, ordinal flag and selector separately and rejects ordinal records lacking
the true gate. Existing archived calendar reports/source versions untouched;
this is metadata clarification, not a trading-risk/behavior change.

Study SHA256:
`f5b0b9a2512aa4de4689b0d0f734bf656db3a8dde235981b543b1f3c703f392a`.
Calendar audit SHA256:
`e989f7f803754b32a51b1f4a118f4784c357e0bc18e87af8359261e715418244`.
579 tests passed/six Torch skipped/four existing sklearn warnings. Three new
payoff tests cover unknown-past exclusion with future candidate retention,
future outcome isolation, raw probability preservation, zero expectancy and
ordinal-vs-true high gate. Fourth new calendar test preserves that distinction.
Frozen prospective model/sources still match. Exposed dates/current universe/
revisions/original delivery/execution assumptions remain limitations. No broker
orders, deployment, increased leverage/budgets, reduced costs, automatic
promotion or real money. Full90% profitable-days objective remains unachieved.

### Historical modeled-boundary quote context — 2026-10-10

Completed GET-only audit `modeled_execution_quote_audit.py`: select40 equally
spaced chronological date/symbol trades from403 corrected causal logistic
trades at probability.65,10bps per side, delay16. Selection never uses P&L,
quotes or favorable spread. Forty distinct dates2025-01-21 through2026-10-01,
not a representative all-market sample or independent validation.

Entry/exit minute boundaries give80 phase observations but only77 distinct
symbol/time queries: duplicate observations are not independent evidence.
All77 queries returned fresh latest-at-or-before boundary SIP quotes within
two seconds, with complete bounded pagination. Conflicting terminal quotes,
invalid quotes, stale quotes and future-only quotes do not fall back to an
earlier favorable snapshot. Median full quoted spread3.5020bps;95th percentile
11.3235bps across77 unique queries. Not measured total trading costs.

Neither boundary is an authenticated execution timestamp: entry bar first
trade can occur after boundary and stop/target exit can occur inside the minute.
Consequently no modeled-fill-vs-quote comparison, price repricing, actual
slippage/fees/impact/queue/fillability claim, raw-size share-unit inference or
cost reduction follows. The receipt contains no authentication headers.
10/20bps assumptions, production engine and frozen forward control unchanged.

Private report SHA256:
`f6792d026b72cdb8900e67053f78872c690382c50083710fdc5de70f691c4c8d`.
582 tests passed, six Torch skipped, four existing sklearn warnings. Three new
tests cover chronological/P&L-independent sampling, duplicate identities,
NY daylight-saving boundary conversion, invalid windows, future/conflicting/
stale/invalid quotes and absence of actual fill or real-cost claims. Frozen
prospective source and model hashes still match. No orders or deployment.

### Past forecast-day support screen — 2026-10-10

`past_forecast_support_research.py` implements a causal permission screen on
the two corrected sparse/split models' existing forecasts. This is NOT a new
fitted predictor, certified probability or independent validation. For every
forecast date, inspect the preceding60 forecast sessions of the UNGATED
counterfactual control at the same probability gate/cost/delay. Require full
60-session warmup, at least20 active control days, positive net control P&L
and the active-day Wilson lower bound at least the original probability gate.
Current/future outcomes are excluded. Flat/no-trade days never count as wins.

Reference control history differs from the gated strategy's realized history;
this is a control-stability screen, not simulated feedback from actual gated
profit. Zero selection score denotes denied permission, not zero predicted
probability; `forecast_probability` retains the original calibrated forecast.
Window overlap, correlated financial days and exposed multiple comparisons
mean the nominal Wilson bound is not guaranteed coverage or a live certificate.

Actual runner exited0:18 original outcomes reproduced exactly (daily/trades/
net) and18 screened outcomes, all36 complete429-session ledgers. All reported
prefix budget/stock/position/risk checks pass; actual broker GET calendar
confirms the full observed span. No target passes. ALL18 screened variants
abstain, yielding zero active days and zero profit, NOT100% accuracy or success.

Primary10bps per side/delay16 control diagnostics across full60-session windows:

| Model/gate | Max active support days | Best control net USD | Highest lower bound with >=20 active days |
|---|---:|---:|---:|
| Logistic .5 |52|-63.53|53.974%|
| Logistic .65 |47|+8.82|61.915%|
| Logistic .9 |2|+3.54|Unavailable|
| Boosted .5 |52|-78.59|59.761%|
| Boosted .65 |34|-17.43|51.519%|
| Boosted .9 |0|0.00|Unavailable|

These maxima may refer to different windows; they are not a combined favorable
state or independent samples. Logistic .65 has20 positive-net windows but
none reaches its65% lower-bound requirement. Logistic .9 reuses the same two
sparse control wins, never meets20-day minimum support. Lowering the criteria
to obtain activity was not done. Screened abstention does not solve the profit
objective. No production strategy/stop/budget/leverage/cost change follows.

Private study SHA256:
`b57289d9830d70a815115e1da73dc875718d83148bb19aa1a37fb99df60c1801`.
Calendar audit SHA256:
`c436c61bceb76a6052cfe51e75456c30bbddb5bf307576493b2792de0d43fed5`.
587 tests passed/six Torch skipped/four existing sklearn warnings. Five new
tests cover current/future-outcome isolation, minimum warmup, no-trade treatment,
full chronological control/permission spans, original probability preservation,
and all possible20..60 active-day count/gate combinations: the existing rounded
Wilson helper changes no decisions for this fixed protocol. Frozen prospective
model and source hashes still match. Goal remains active and unachieved.

### Own-label balanced1% target — 2026-10-10

`balanced_target_simulator.py` is an isolated copy of the causal sparse
simulator, with predeclared .4% control and1% alternative targets only. Original
source unchanged. Stop remains1%, horizon60 minutes, same stock/category/
position/planned-risk caps, raw gap losses, conservative same-bar stop-first,
10/20bps per side and delay16/17. A later exit can lengthen exposure inside the
same horizon; no extra sizing, loss relaxation, leverage or production change.

`balanced_target_research.py` uses corrected date-effective split features,
all causal opening candidates and its OWN past1%-target labels/calibration.
Only known past filled outcomes train; unknown future candidates still get
forecasts before selection. Missing selected outcomes stop the entire cumulative
ledger. This is not the first target study: earlier studies used different
inputs/full-session filters. Exposed outcomes remain development evidence.

Actual runner exited0,44 newly fitted chronological folds with no unresolved
warnings. All18 .4% control daily/trades/net/unknown outcomes exactly reproduced.
All36 control/new outcomes complete429-session ledgers; all reported prefix risk
checks pass and actual broker GET calendar confirms span. No target passes.

Primary10bps per side/delay16,1%-target own-label models:

| Model/gate | Active days | Winning percent | Net USD |
|---|---:|---:|---:|
| Logistic .5 |75|48.00|-201.32|
| Logistic .65 |2|100.00|+14.01|
| Logistic .9 |0|Unavailable|0.00|
| Boosted .5 |23|26.09|-159.13|
| Boosted .65 |1|0.00|-27.10|
| Boosted .9 |0|Unavailable|0.00|

The positive .65 logistic sample is2025-10-06(+6.6406USD) and2026-06-08
(+7.3703USD): two different dates from the .4%-target/.9 control's two wins,
but still exposed, sparse and NOT independent evidence. Wilson interval
[34.237%,100%], far below required lower bound. Higher costs retain only one
day/+4.97USD; delay17 retains only one day/+7.37USD. All three positive variants
reuse subsets of the same TWO observations, not independent discoveries.

Algebra, NOT a forecast: with ideal target/stop-only exits and10bps per side,
.4% target has approx .1994% net gain versus1.1978% net stop loss, requiring
85.7286% winning TRADES for break-even.1% target changes ideal gain to .7982%
and break-even to60.0100%, without changing ideal stop loss. It does not create
better entries,90% winning DAYS, or account-level1% daily profit. Gaps, horizon
exits, execution uncertainty and actual costs invalidate the idealized ratio.
At20bps, the .4% ideal target gain is negative; its algebraic break-even exceeds
100%, meaning no feasible target/stop-only win fraction, not a probability claim.

Study SHA256:
`e8a6420ad96a0ae4f114dfcbb31dd666d5ed04b830e551a4512d5e5f043a5db3`.
Calendar audit SHA256:
`aeb4843b73b3a8de39441f678b38a6933daafbdb323068da4c4fd24c030927c0`.
593 tests passed/six Torch skipped/four existing sklearn warnings. Six new
tests cover control path/portfolio equivalence, unchanged stop/quantity/risk,
later-exit missing observations, no restarting after unknown, gap overshoot,
same-bar stop-first, own-label past-only fitting/future isolation and algebra.
Frozen prospective source/model hashes still match. No orders/deployment/live
money or promotion. Full90%-profitable-active-days objective remains unachieved.

### Fixed causal/split shadow comparator bundle — 2026-10-10

Existing `control_v2` collector uses21 old features and is NOT the16-feature
causal/split-normalized research model. Do not attribute its future results to
the corrected or1%-target models. Existing collector, model, manifest, sources
and cloud schedule remain unchanged; both old source/artifact checks pass.

`causal_shadow_bundle.py` now fits/freezes two logistic/calibrated shadow heads
at `research_prospective/causal_split_shadow_v1`: targets.4% and1%, same16
date-effective split inputs and separate OWN past known-filled labels.
Training6034 and6019 rows respectively, past calibration598 rows each.
Training date groups end2026-07-08, calibration2026-07-09..2026-10-01; declared
strictly future forward start2026-10-12. No retraining after freeze, model
promotion, budget/risk/cost change, trading API writes or production deployment.
Both heads are failed-exploration COMPARATORS, not approved profitable candidates.

Actual freezer completed, models serialized and reloaded with exact own
artifact/source/runtime checks. Artifact6921 bytes, no raw provider bars or
credentials. Fixed threshold.65,10bps per side/stress20, fifteen-minute assumed
information delay plus one-minute entry latency,60-minute horizon,1% stop,
stock1%/category5%/three positions/planned risk.05%. Existing control stays fixed.

Pure inference validates complete30-bar current packets, no later current bars,
no future historical dates, fresh prior terminal context, matched fixed universe
and finite consistent OHLCV. It retains all causally eligible candidates and
returns BOTH probabilities without orders. Pure inference is explicitly NOT
an authenticated prospective observation: receipt provenance, pre-entry external
timestamp anchor, collection failures/missed sessions and outcome audit are
still required. No collector or cloud job yet exists for THIS bundle. Forward
observations remain ZERO. Do not report this setup as forward validation.

New artifact SHA256:
`01a5997c7780bb14142248cc3a8db12c1ee62d923bd74842e7358c02bf76c45e`.
New manifest SHA256:
`27174cbfc11b1a90fd3ab203de33ffb50c6530643507810712fd60f350b7f145`.
`requirements-causal-shadow.txt` separately pins the serialized core runtime,
including threadpoolctl; production requirements unchanged.599 tests passed,
six Torch skipped/four existing sklearn warnings. Six new tests cover exact
original logistic/calibration prediction parity, disjoint fitting dates/future
label isolation, research input parity without future close, invalid/incomplete/
future/stale input rejection, future split isolation, overwrite rejection, and
artifact hash verification before deserialization. This closes a model-identity
gap in preparing the actual comparative test, not the profitability objective.

### Separate shadow collector registered and cloud-validated — 2026-10-10

`causal_shadow_collector.py` adds separate GET-only prospective collection for
the fixed causal/split shadow bundle. Parent model/manifest/description are
unchanged: the description's earlier `collector_implemented=false` is retained
as a historical freeze-time statement, not retroactively edited. Current
collector protocol is the separate immutable `collector_protocol.json`.

Protocol SHA256:
`c7a26c74323e7966b08a23eadb7bfdabf2fec7b4e2e31a414d71b735551e2241`.
Its collector/crypto/requirements sources are fixed at commit
`7dec3a115c0ad4c0fef7edca7f5e724679e4228f`, before future cutoff2026-10-12.
New `.github/workflows/causal-shadow-prospective.yml` checks out that exact commit.
Its summer/winter weekday schedules are NY-time gated; manual dispatch defaults
to VALIDATE ONLY. Existing control_v2 collector/workflow/source/model untouched.

Collection prepares100-calendar-day SIP/raw historical context before the
capture window; CSV/metadata hashes are retained and rechecked. Strict prior
dates, raw complete30-minute opening timestamps, calendar horizon, current
corporate-action pagination and receipt clock chronology are checked. Any late
input/inference/retention fails without a forecast claim. No backfill or overwrite.
Historical SDK receipts do NOT prove original historical delivery/revisions;
missing timestamps/duplicate/future/off-minute opening bars fail closed.

Public packets contain paired probabilities, receipts' hashes and local timing,
NOT raw provider bars or signal prices. Raw opening/calendar/splits/history and
full inference snapshots stay private, encrypted with the dedicated256-bit
evidence key AFTER public forecast upload. Broker secrets are never encryption
keys. A captured packet remains locally evidenced/external-anchor-pending;
upload-step completion plus one second must be independently verified before
the hypothetical entry, not inferred from artifact creation or local flags.

Actual GitHub validation-only run38080987609 completed SUCCESS:
https://github.com/dsarsham-cmyk/autotrader/actions/runs/38080987609
Linux Python3.12 pinned runtime, both frozen heads, source/protocol integrity and
dedicated key passed. Collection/encryption of trading-day inputs were SKIPPED.
Downloaded actual artifact11679858830 has verified ZIP SHA256:
`d6ede8f366b5a21c22db64cc6edb50b2e4e561e6567d0d041b2a6598b0e0f5b6`.
It contains ONLY `research_runs/causal_shadow_cloud_status.json`, reporting
`shadow_environment_validated_only`, zero sessions, ordersfalse, independent
validationfalse. Not a forward observation or profitability result.

606 tests passed/six Torch skipped/four existing sklearn warnings. Seven new
collector tests cover exact raw timestamps (including nanoseconds), incomplete/
duplicate/future packets, DST/weekends, private snapshots/public minimization,
immutable capture, late data/inference, history hash/feed, calendar/pagination,
and status safety flags. Local parent/new collector checks and old control
source/artifact checks still pass. No broker writes, production deployment,
automatic promotion, increased budgets/leverage/loss limits or real money.

New shadow AFTER-CLOSE AUDITOR IS STILL PENDING. Existing control_v2 auditor
does not understand this paired-probability schema; do not count its results for
these heads. Need independent upload anchor verification, private-data recovery,
exact input/inference reproduction, all scheduled/missed/failed session discovery,
and separate continuous budgeted outcome ledgers. Scheduled collection can miss
deadlines; those are missing evidence, not wins or backfilled observations.
Genuine forward observations remain ZERO. Full objective remains unachieved.

### Paired shadow provenance/outcome audit cloud-verified — 2026-10-10

`causal_shadow_replay.py` verifies the paired packet/parent/collector hashes,
GitHub run identity/branch/attempt, receipt chronology and successful upload
completion plus one-second upper margin BEFORE entry. Artifact creation alone,
missing upload completion, alternate attempts/ownership or local flags cannot
establish a timely anchor. Dedicated encrypted snapshots are recovered safely;
every retained CSV/metadata/current opening/calendar/split/inference hash is
checked, history rebuilt, and actual frozen heads recomputed against published
probabilities (fixed1e-8 absolute tolerance) and retained decision prices.

`causal_shadow_audit.py` discovers ALL terminal/pending producer runs, including
failed ones, with strict duplicate/total-count pagination checks. Current input
opening must exactly match subsequently fetched outcome opening; revisions do
not silently change decision information. Outcome data is limited to the first
108 minutes and may have missing future bars: no full390-minute completeness
filter. A selected missing path stops that head's whole cumulative ledger.

Each head is an ALTERNATIVE virtual sleeve, not simultaneous real account
allocations. One100k initial virtual capital per comparison, no daily resets,
same fixed .65 gate, costs10/20bps/delay16/17, budgets/stops/guards. First missing
or duplicate forecast stops continuous replay; later verified observations are
listed as unreplayed rather than skipped to improve equity. Full interval net
and win rate remain UNKNOWN for incomplete/pending/error evidence. Valid empty
eligible sets get explicitly marked computational calendar rows with zero
selection, never invented forecasts or wins. Stress-only success cannot qualify
the primary10bps/delay16 policy. Technical/simulated screens never promote models.

Current provenance counts distinguish verified forecasts from outcome-ready
forecasts; individual model ledgers also distinguish input coverage from missing
selected price paths. Reports record audit-source hashes and parent manifest.
Broker execution, actual stop protection, original historical delivery and
independence of correlated financial days are not certified by this OHLC replay.

New `.github/workflows/causal-shadow-outcome-audit.yml` is active, weekdays21:30
UTC (after close/delayed-SIP buffer in both DST seasons). Manual default is
validate-only. Actual non-validation GET audit run38082023382 completed SUCCESS:
https://github.com/dsarsham-cmyk/autotrader/actions/runs/38082023382
Actual downloaded report artifact11681220385 has verified ZIP SHA256:
`2bff512ca49100a829e69c854b3bc1f65e4f168f976477d59a6b4698a736e835`.
It contains ONLY `results.json`: zero completed/verified/outcome-ready sessions,
no retrieval failures or pending producer runs, performance/independent screens
false and ordersfalse. Before first declared forward date2026-10-12, this is
expected empty evidence, not a trading result or validation success for90%.

614 tests passed/six Torch skipped/four existing sklearn warnings. Eight new
tests cover strict external timing/ownership/attempts, prediction integrity,
retained opening revisions, sparse future prices, continuous capital/missing
dates, empty vs valid abstention/duplicates/pending/unknown outcomes, complete
discovery pagination, stress-only success exclusion, and a dedicated-key
encrypted SYNTHETIC canary reproducing both actual frozen heads. Fixture packet
is explicitly `fixture_not_prospective`, never published as genuine evidence.
Both old control and new shadow protocol/source/artifact checks still pass.

Durability remains open: public GitHub Actions artifacts have maximum90-day
retention. Source: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
100 active-day qualification exceeds that time span. Local immutable backups
exist, but automatic long-term cloud encrypted backup is NOT implemented or
authorized yet; approval requested separately for an unpublished draft-release
backup, or local-only preservation. No draft/release was created. Expired or
unavailable evidence fails closed; it must not be silently dropped or counted
as no-trade days. Existing collector/workflows/bot unchanged; no live trading,
new orders, budget/leverage/loss relaxation or production deployment. Goal active
and unachieved: scheduled plumbing is not the requested profitable formula.
