# Paper-trading remediation — 22 October 2026

## Mandate and scorekeeping

User clarified the goal: 90% of **active days** profitable by 31 October,
not 90 distinct days. This is a target to measure, not a promised outcome.
An active day includes executions or exposure; liquidation does not erase a
losing day. A winning day has strictly positive total daily P&L after costs,
including marked open exposure. Zero is not a win. Missing evidence is unknown,
not inactivity. Report net cumulative P&L, drawdown, risk breaches and sample
size alongside the observed percentage. Separate historical exploration,
prospective shadow simulations, and broker paper executions. Multiple models
on one date do not create multiple independent days.

No live trading, extra leverage, relaxed stops, new subscription or deployment
is authorized by this document. Existing user directions govern those actions.

## Verified audit findings

- Both October 22 exits were engine-requested market orders, not broker stop
  or take-profit fills. The original reason cannot be established from the
  generic completion message. Protection-recovery timeout is a hypothesis,
  not a confirmed historical diagnosis without the original logs.
- The 18 scheduled forecast producer runs inspected for October 12–22 had no
  artifacts. The latest collection steps were skipped after their preparation
  window. Green workflow completion did not establish a forward observation.
- The October 22 shadow audit reported zero verified forecast sessions:
  https://github.com/dsarsham-cmyk/autotrader/actions/runs/39697892057
- The control audit crashed trying to write/read an inspection in a missing
  run directory when no artifact had created that directory.
- Existing matched historical analysis remains exposed exploration: the
  logistic daily filter at gate 0.65 had 42 active days, 69.05% winning and
  -50.92 USD net. It does not validate the requested target.

## Local repairs and boundaries

1. Both outcome inspectors retain a missing-evidence inspection even when
   artifacts are empty, without manufacturing forecasts or no-trade days.
2. Both workflow definitions retain an explicit unavailable-evidence status
   when collection/validation produced none. Missing expected status fails
   the step; upload treats absence of all files as an error. Frozen checkout
   refs, model files and hashed collector source remain unchanged.
3. Paper controller records the first observed liquidation cause, symbols,
   repair phase and timing, and preserves it through completion/restart.
   This instruments existing behavior; it does not change liquidation scope,
   protection recovery timeout, order sizing or stop requirements.

These repairs do **not** make GitHub scheduling punctual. The skipped winter/
summer alternative can still be an expected technical skip. The retained
status, packet provenance and pre-entry external timestamp—not workflow
colour—decide whether a session has evidence.

## Unresolved operational work

- Restore Railway authentication, then inspect the original October 22 logs.
- A separately supervised collection runtime with authenticated external
  pre-entry timestamping is still required to remove dependence on GitHub
  cron latency. Do not silently replace the frozen producer or count a new
  producer as the old experiment. Register and test any replacement protocol.
- Verify a future actual collection before calling the forward pipeline
  restored. Lost prior sessions cannot be backfilled into forward evidence.
- Local test success is not deployment success or evidence of profitability.

## New research direction

`late_day_spy_long_v1` is an isolated exploratory adaptation of intraday
momentum: morning return including overnight conditions a final-session long
entry. Its protocol must be fixed before running, with an otherwise identical
unconditional-long control, explicit delayed information, realistic execution
costs, official calendar and existing risk constraints. Its results must not
be promoted automatically or substituted for the running paper strategy.

Primary motivation: https://doi.org/10.1016/j.jfineco.2018.05.009
The adaptation does not inherit the paper's performance or prove 90% wins.

## Verification and continuation — 31 October 2026

The previous turn made concrete progress: local regression fixes and a completed
fixed-rule exploratory study, not merely a plan. They were not yet published.
There was no verified live process to wait for when this continuation started.

- Full current checkout: **680 passed, 6 skipped**, four pre-existing sklearn
  deprecation warnings. Optional skipped tests are not claimed as verified.
- Both frozen model/collector bundles retain their original source contracts;
  the new study and reporting fixes do not replace those experiments.
- The first late-day report is preserved byte-for-byte. An accounting-report
  extension reproduces all six original trade/daily ledgers exactly.
  Principal signal: 202 active days, 12 wins (5.9406%), -262.1746 USD,
  0.2622% end-of-day drawdown on the virtual 100,000 USD account.
  Matched unconditional control: 351 active days, 6.2678% wins, -479.78 USD.
  Neither cost/delay stress is profitable. This candidate is rejected under
  the registered assumptions, not retuned after seeing its result.
- Late-day inputs are retrospective SIP/raw prices, official calendar, and a
  SPY-specific complete split receipt (zero splits). They are not original
  delivery-time evidence. No independent/prospective or production approval.
- Current shadow audit artifact digest verified: run **41153004234**, artifact
  **13024325149**. All 15 completed sessions from October 12–30 are missing;
  zero verified forecast and zero outcome-ready sessions. Latest control audit
  **41152851979** still failed under the old published inspector.
- Published account history for October 1–30 has 20 dates with executions,
  11 positive dates (55%), and cumulative reported daily change -337.89 USD.
  This is broker paper history, not independent validation of a new predictor.
  Exposure-only days were not independently reconstructed for this summary.
- Railway CLI authentication remains unauthorized. Production health responds
  200 and still advertises the old October 7 controller. Deployment of local
  liquidation diagnostics is therefore not verified.

The goal remains unachieved. The first future authenticated forecast is still
an operational acceptance requirement; retaining a missing-status artifact
does not satisfy it. Continue with a registered reliable collection runtime
and independent observations, not with retrospectively manufactured forecasts.
