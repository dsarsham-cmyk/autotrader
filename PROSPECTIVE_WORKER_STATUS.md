# Isolated prospective worker — 31 October 2026

The 90% profitable-active-days objective is **not achieved**. No experiment in
this document is approved for production orders or real money.

## Concrete progress

- `calendar_shadow_bundle.py` fits and freezes two research-only logistic heads
  on the audited calendar-correct historical inputs through October 1. Training
  ends July 8; calibration is July 9–October 1. Its original explored variants
  failed the performance target. These are comparators, not a newly profitable
  strategy or independent evidence.
- Frozen directory: `research_prospective/calendar_shadow_v1`. Manifest:
  `c816ccf0852f291f67072101bd311341a72d88f8641f454e70f43a7c8069a14f`.
  Earliest prospective start: November 2. Source closure and numeric runtime
  are verified before loading the own serialized model. Prior-close inference
  requires the actual last official regular-session bar, including half-days.
- `prospective_worker.py` is a separate, persistent collector with NY/DST
  scheduling, prior-only preparation, an OS process lock, write-once daily
  capture, dedicated encrypted evidence, and no order path. It does not depend
  on the GitHub cron to begin capturing inputs. A dispatch remains only pending
  until its uploaded packet is verified before entry.
- `calendar_worker_replay.py` decrypts a committed private archive and reproduces
  inputs, candidate membership and frozen probabilities. It rejects future or
  corrupt data, incomplete receipts and unsafe archives. Reproduction alone
  does not authenticate timing or establish profitability.
- `research_clock.py` rejects incompatible clocks; it does not adjust UTC or
  rewrite timestamps. A real probe on this workstation failed with roughly
  21 seconds discrepancy. The research worker must stay blocked here until the
  clock is demonstrably consistent. HTTP Date is a consistency check, not NTP
  or proof of absolute UTC.
- `requirements-calendar-worker.txt` pins the separate Python 3.12.10 numeric,
  SDK and network dependency closure. Production dependencies are unchanged.

## What the cloud probes proved and did not prove

The fixed Actions branch `research-anchor-v1` points to
`080194c4a75422e99ee109c6c0ddba08ceba4fbc`. It has no broker secrets or trading
code. It records only validated public prediction envelopes and their hashes.

Two synthetic canaries were executed once each:

- [41219171412](https://github.com/dsarsham-cmyk/autotrader/actions/runs/41219171412):
  the local clock did not agree with GitHub timing; original verdict FAIL.
- [41219459959](https://github.com/dsarsham-cmyk/autotrader/actions/runs/41219459959):
  early API titles and queued-job start metadata changed during initialization;
  original creation-time/late-artifact proposal also remains FAIL.

We did **not** loosen the timing requirement or retroactively pass those tests.
The simpler ORIGINAL completed-upload rule was separately verified against the
second run's authenticated artifact and job metadata: upload 16:23:37 UTC,
conservative bound 16:23:38, before its synthetic 16:23:40 entry. The ZIP digest,
bytes, actor, attempt, branch, script and workflow hashes matched. The public
summary is `research_prospective/calendar_shadow_v1/transport_probe.json`.

Run creation, a hash in the run title, a successful POST, or a late upload is
**never** sufficient. If the direct-dispatch runner is delayed beyond entry,
the future market observation is unverified. This is still a best-effort
transport with a strict acceptance gate, not a punctual-execution guarantee.

**Zero market observations** came from these probes. No model performance,
paper order, production approval or independent validation is inferred.

## Unfinished operational acceptance

1. Railway authentication still needs restoring before deployment or inspection
   of the original protection-failure logs. Production engine was not changed
   by this work. Do not create a paid extra service without verifying the
   existing EUR 10/month authority and resource envelope.
2. Worker requires its own narrowly scoped GitHub Actions credential and the
   dedicated evidence-encryption key in its deployment environment. Never paste
   secrets into chat or reuse a broker secret as an encryption key.
3. A persistent private volume is required. Only hashes/probabilities are sent
   to the public repository; encrypted input bytes must remain recoverable.
   No external release/storage service was silently created.
4. Verify the deployment clock, source lock, runtime, volume and scheduling.
   Then collect an ACTUAL future-session packet, confirm successful upload
   before 10:16 NY, reproduce its private inputs, and audit outcomes later.
5. A separately scoped new-cohort outcome report is still needed. Missing old
   October sessions remain missing, not backfilled or relabelled. No independent
   forward claim is possible before actual observations and complete coverage.

Registering an immutable future protocol and passing technical tests do not
complete these acceptance steps or the profitability objective.

## Final technical verification for this implementation

- Published implementation: `7f14e7efebf28f6983e1c06a2a6e79ccce78210d`.
- Registered worker protocol:
  `695142f715db843b5fd3d6991c21b8baab730b34efc128ff2ca31aa185f969e1`.
- Local tests: **812 passed, 6 optional skipped**, four existing sklearn
  deprecation warnings. Focused new-component tests: **132 passed**.
- Initial Linux QA [41220751037](https://github.com/dsarsham-cmyk/autotrader/actions/runs/41220751037)
  failed before installing dependencies: `ubuntu-latest` had moved to Ubuntu
  26.04, without the registered Python build. This failure is retained.
- Runner was explicitly pinned to Ubuntu 24.04 in commit
  `4566b68ea182cd244c444571c906921c9adb333f`, without changing Python or the
  frozen model/runtime. New QA
  [41220879542](https://github.com/dsarsham-cmyk/autotrader/actions/runs/41220879542)
  completed successfully on CPython **3.12.10**. All **34** worker/audit source
  files, model contracts, exact package versions and the clock guard passed.
- Artifact **13049314893**, ZIP digest verified against GitHub:
  `8952f87705da9ac51ba8a4ab3093a31ed3793bb57e3888113965d388f20151e1`.
- Linux clock sample: local `16:41:56.800584 UTC`, remote Date `16:41:56 UTC`,
  RTT `0.07938 s`; no timestamp adjustment. This does not establish the Railway
  deployment's clock or repair the inconsistent local Windows clock.

The cloud validation result is explicitly `technical_environment_validated_no_forecast`:
zero sessions, no broker requests/orders, no deployment, no verified private
volume and no independent validation. GitHub CI success does not start a
persistent collector. The startup date is a predeclared experimental boundary,
not a promise that deployment or data collection will have happened by then.
