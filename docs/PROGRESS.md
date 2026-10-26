# PROGRESS.md

Living log. Update after each task and phase so the current implementation state and evidence stay visible.

## Current status
- Current phase: P5 active verification (P4 complete)
- Event clock at last update: 2026-10-26 (start time = 2026-10-26 00:00 local)
- Last green `make check`: 2026-10-26
- Tags: none
- Continuation session: P0 and P1 are complete and pushed. P2 detector implementation, validation-only calibration, one-time held-out measurement, and diagnostic exports are complete.

## Phase log
| Phase | Status | Budget | Used | Gate evidence | Notes |
|---|---|---|---|---|---|
| P0 Bootstrap | complete | 0.75 h | | `make setup && make check`; `make dev`; fresh source-copy setup/check; committed-tree `make check` | 14 backend tests and 1 frontend test passed at P0 completion; P0 reverified after push. |
| P1 Plant/twin | complete | 3 h | | `make check`; `make fit-twin`; `make plot-nominal`; user reviewed figure | 22 backend tests and 1 frontend test pass; all MUST criteria met. NASA P1b unavailable and unsupported. |
| P2 Passive detection | complete | 3.5 h | | `make check`; `make calibrate`; `make eval-passive` | Validation 0.1200 FA/h meets target; held-out test 0.2101 FA/h is reported above target without retuning. |
| P3 Attack engine | complete | 3 h | | `make check`; `make stealth-report`; `attacks-frozen` tag | AT1–AT6 and seven scenarios implemented; all SPEC 6 stealth criteria pass on validation seeds 0–99. |
| P4 Localization | complete | 2 h | | `make localization-report`; localization unit tests; `make check` | Validation threshold and dominance ratio calibrated; AT1 and AT2 confusion matrices recorded on seeds 0–99. |
| P5 Active verification | complete with AT4 limitation | 3.5 h | | `make probe-report`; probe tests; `make check` | Fresh keyed probes, safe amplitude clipping, gain detectors, validation calibration, sweep, overhead, and AT6 oracle results recorded. AT3 is exposed; active verification does not improve on B2 for AT4 and its reported-current input is the suspected cause. |
| P6 Guard/response | todo | 3 h | | | |
| P7 Evaluation | todo | 3 h | | | |
| P8 API | todo | 3 h | | | |
| P9 Frontend | todo | 8 h | | | |
| P10 Hardening | todo | 4 h | | | |
| P11 Submission | todo | 3 h | | | |

## P0 completion evidence
- `make setup` followed by `make check` passes in the project workspace: Ruff, strict mypy, backend pytest (14 passed), frontend Vitest (1 passed), ESLint, TypeScript, and Vite production build.
- Repeated setup and full checks in a clean source copy without `.git`, virtual environments, dependencies, caches, or build outputs; all gates passed.
- `make dev` started Uvicorn and Vite; `/api/health` returned HTTP 200 JSON, startup logged config hash `87950a9351118e47`, and Ctrl+C stopped the services cleanly.
- Later-phase Make targets are present and fail loudly with `not implemented in this phase`; confirmed with `make calibrate`.
- IBM Plex font assets are bundled with the frontend build; no font CDN is required.
- The workspace initially had only the README tracked. P0 was later split into ten commits and P1 into eight commits, both pushed to `origin/main`.

## P0 re-verification after push
- Re-ran `make check` from the committed tree after the ten P0 commits were pushed: Ruff, strict mypy, backend pytest (14 passed), frontend Vitest (1 passed), ESLint, TypeScript, and Vite production build all passed.

## Confirmed root causes and fixes
- Frontend could not build because `src/App` was absent, Vitest globals lacked types, and the PostCSS config used CommonJS in an ESM package. Added a minimal app, explicit Vitest/jest-dom imports, and ESM PostCSS config; frontend checks now pass.
- Make targets hid ESLint, mypy, and TypeScript failures and referenced a nonexistent backend path. Reworked targets to run actual checks, fail on errors, support Windows paths, and added missing typecheck and development supervision scripts.
- Backend strict checks exposed partially implemented plant/twin code with undefined names, incorrect config access and thermal equations, weak covariance handling, and missing validation. Repaired these issues and added deterministic simulation, validation, and EKF regression coverage.
- Test setup failed to provide the HTTP client dependency required by the installed Starlette test client. Declared the compatible test dependency and generated a pinned requirements lock.
- Config loading, timestamp handling, package metadata, and startup logging had gaps; fixed config validation/defaults, timezone-aware JSON timestamps, package typing metadata, and startup config-hash logging.
- The initial CC/CV request logic could fall back to fast-charge current after voltage relaxation, overshooting the voltage limit. Made the controller latch in CV once entered; honest one-hour peak voltage is now 4.1937 V.

## P1 implementation and evidence
- Added seeded Gaussian sensors with configured quantization, rated-current limiting and reported-temperature derating, a latched CC/CV upstream controller, and an integrated plant/sensor/charger loop.
- Added deterministic per-unit variation for capacity, resistances, thermal resistance, and OCV offset. Verified 200 seeded varied units produce finite trajectories.
- `make fit-twin` fits the one-RC polarization response on attack-free synthetic validation data using seed 10000 and records `R1_n=0.001083371522 Ω`, `tau1_n=55.23743011 s`, and `0.00228423 V` polarization RMSE in `configs/default.yaml`.
- `make plot-nominal` writes `docs/screens/p1-plausibility.png`. Seed 11 honest run: peak T 45.98 °C, peak V 4.1937 V, final SOC 0.9444. Under-reported temperature is held at 30 °C and reaches 55 °C at 23.10 min. The 150 A CV hijack begins at 54.67 min and reaches voltage hazard after 141 s.
- P1 gate `make check`: backend pytest 22 passed; frontend Vitest 1 passed; Ruff, strict mypy, ESLint, TypeScript, and production build passed. Scripts also pass Ruff.
- `data/raw/nasa/` is absent. No NASA file was scraped or available for optional P1b; public-dataset validation claim is marked unsupported in `CLAIMS_EVIDENCE.md`.

## P2 implementation and evidence
- Added a 30-sample sliding NIS sum detector, two-sided per-channel CUSUM with deadband and reset-on-alarm, and static/rate-based range checks. EKF results expose innovation standard deviations for residual standardization.
- Corrected the EKF to use the configured twin OCV curve consistently in voltage prediction, SOC slope, and current residual calculation. A synthetic linear-Gaussian test reports mean NIS 1.998 (2 degrees of freedom) and mean NEES 2.883 (3 degrees of freedom), both inside 99% chi-square bounds; singular innovation covariance still raises `NumericalError`.
- `make calibrate` used only validation seeds 0–99 and wrote `configs/detection.yaml` with config hash `6d079b3bd6bc4947`, date `2026-10-26`, NIS window-sum threshold 93.1451, and CUSUM threshold 3.46747. Each tunable detector family used six false-alarm episodes of calibration budget; range checks had none.
- Validation result: 12 combined episodes / 99.97 hours = 0.1200 false alarms/hour, below the 0.20/hour target. `data/results/nis_qq.json` contains validation observed quantiles and chi-square df=2 comparison data.
- Measured held-out test seeds 100–199 once with frozen thresholds. Result: 21 combined episodes / 99.97 hours = 0.2101/hour, slightly above target. No test-driven threshold changes were made; the claim is softened and the result recorded under Claims at risk.
- P2 `make check`: backend pytest 29 passed; frontend Vitest 1 passed; Ruff, strict mypy, ESLint, TypeScript, and frontend production build passed. Calibration code rejects duplicate or held-out seeds.

## Deviations, risks, and cuts
- The P0 clean-room verification used a fresh source copy with generated environments/dependencies/build outputs excluded, not a Git clone, because project implementation files are untracked user work.
- `npm ci` advisory counts are unchanged; dependency remediation remains parked for a compatibility-focused update.
- AT4 private-twin input uses the attacker-visible reported current channel and adds no second sensor-noise draw to it. A model driven only by its nominal current estimate caused 97% B2 catches on validation seeds; the corrected telemetry-only estimator produced a 27% catch rate, while never receiving actuator-command or probe fields. This is recorded before the P3 freeze.

## P3 implementation and evidence
- Implemented AT1 spike bursts, AT2 slow temperature drift, AT3 replay plus a 2.5× cooling-resistance fault, AT4 model synthesis with 5% private-twin R0 error and no command/probe access, AT5 150 A CV/SOC-triggered requests, and AT6 oracle limit case. Added scenario catalog and story ladder.
- Added configurable physical cooling degradation to the stateful plant and an undefended attack runner that reports true state, forged telemetry, requests, and B0/B1/B2 alarms.
- `make stealth-report` completed 600 simulations across validation seeds 0–99 (100 per attack), using unchanged P2 thresholds and config hash `6d079b3bd6bc4947`.
- Detection rates: AT1 B0/B1/B2 100%/100%/100%; AT2 0%/32%/90% (B2 median delay 1165.5 s); AT3 3%/96%/100%; AT4 0%/2%/27%; AT5 100%/2%/4%; AT6 0%/5%/21%. Rates and delays are in `data/results/stealth_report.json`.
- Hazard reachability is covered by the held-at-30°C thermal test and 150 A CV command test; the AT5 attack runner also crosses voltage or SOC hazard on validation seed 17. Static bounds applicable to AT1–AT5 and the AT4 knowledge boundary are covered in `backend/tests/test_attacks.py`.
- Backend: 43 tests passed; Ruff and strict mypy passed. Frontend: 1 test passed; ESLint, TypeScript, and production build passed.
- P3 attack config is frozen at commit/tag `attacks-frozen`; parameter changes now require a logged deviation and user approval.

## P4 implementation and evidence
- Added full, V-only, and T-only EKF tracks. A 60-second rolling window combines standardized full-model residuals, cross-prediction residuals, and current consistency into V/I/T evidence scores.
- Localization decisions support `v`, `i`, `temp`, `multi`, `command`, `unknown`, and `none`; `eval/metrics.py` implements SPEC multi-channel scoring and ambiguous-case accounting.
- `make localization-report` calibrated the evidence threshold to 3.8950 (99.5th percentile of 359,900 channel-max samples across clean validation runs 0–99). Dominance ratio candidates 1.25–3.0 were evaluated on tuning seeds 0–49; selected ratio is 3.0. Candidate ratios gave equal tuning accuracy, so the selection is a deterministic tie-break, not a demonstrated performance advantage.
- Validation confusion: AT1 temperature-dominant → temp 100/100 (100%); AT2 temperature-only drift → temp 85/100 (85%), unknown 5/100, none 10/100. Multi is ambiguous for these scenarios. Full matrices and per-run predictions are in `data/results/localization_report.json`.
- Synthetic voltage-only and temperature-only sensor steps both localized to the correct channel. Tests cover multi, command override, unknown, none, reset behavior, scalar EKF updates, and confusion scoring.
- P4 verification: 51 backend tests passed; Ruff and strict mypy passed; frontend test, lint, typecheck, and production build passed.

## P5 implementation and evidence
- Added keyed, nonce-fresh balanced PRBS probe generation, safe clipping against current, voltage, and thermal bounds, periodic and continuous scheduling, and gain estimators for voltage-only, current-only, and combined evidence.
- Calibrated on 600 attack-free windows from seeds 0–99. The combined threshold is `g_min_V=0.37245`, `g_min_I=0.99`; measured combined false alarms are 0.19/hour (target 0.20/hour). The calibration records and checks the unchanged P2 config hash `6d079b3bd6bc4947`.
- At the default 4% probe amplitude on 100 validation seeds: AT3 is detected 100% by V-only, I-only, and combined gain; median V/I gains are -0.0094/-0.0051. AT4 is detected 0%/3%/3%; median gains are 1.0436/0.99976. B2-with-probe detects 29% of AT4 runs, versus the existing no-probe B2 rate of 27%, so active verification does not meaningfully beat B2 on AT4. AT6 oracle detection is 0%/3%/3%, showing the expected limit.
- Diagnosis: P3 AT4 estimates voltage from attacker-visible `I_rep`; the probe is present in that channel, so the private twin reproduces its voltage effect and yields gain near one. Resolving this requires changing the frozen P3 AT4 knowledge/model contract. P5 reports the limitation without silently changing the frozen attack.
- Mean paired overhead across 20 runs: peak temperature +0.0118 °C, final temperature +0.0020 °C, time to 90% SOC +1.25 s, estimated efficiency change −0.000137 percentage points. The sweep uses 20 clean calibration seeds and 20 separate attack seeds per amplitude; each point meets 0.20 false alarms/hour. AT3 combined detection is 100% throughout; AT4 combined detection is 10% at 0.5–3% amplitude and 0% at 5–8%, below B2. See `data/results/probe_report.json` and `data/results/probe_amplitude_sweep.svg`.
- Probe tests and the full backend test suite pass. Ruff passes for backend source/tests and the new report script; strict mypy passes for all 28 backend source files. Frontend Vitest (1), ESLint, TypeScript, and production build pass.

## Exact continuation point
- Next: begin P6 guard/response.
- P0 was pushed in ten commits and P1 in eight focused commits; P2 was committed in five focused commits. P3 freeze is recorded by the `attacks-frozen` tag.

## Measured numbers log
`P0 | make check | backend tests | 14 passed | — | 87950a9351118e47`
`P0 | make check | frontend tests | 1 passed | — | —`
`P0 | npm ci | dependency advisories | 15 (6 moderate, 7 high, 2 critical) | — | —`
`P1 | make plot-nominal | honest peak T / peak V / final SOC | 45.98 °C / 4.1937 V / 0.9444 | 11 | —`
`P1 | make plot-nominal | under-reported thermal hazard time | 23.10 min | 11 | —`
`P1 | make plot-nominal | 150 A CV hijack to voltage hazard | 141 s after attack onset | 11 | —`
`P1 | make fit-twin | R1_n / tau1_n / polarization RMSE | 0.001083371522 Ω / 55.23743011 s / 0.00228423 V | 10000 | —`
`P2 | make calibrate | validation combined FA/hour | 0.1200/h (12 episodes / 99.97 h) | 0–99 | 6d079b3bd6bc4947`
`P2 | make eval-passive | held-out test combined FA/hour | 0.2101/h (21 episodes / 99.97 h) | 100–199 | 6d079b3bd6bc4947`
`P2 | synthetic linear EKF | mean NIS / mean NEES | 1.998 / 2.883 (99% chi-square bounds) | 20261026 | —`
`P3 | make stealth-report | B0/B1/B2 rates for AT1 | 100% / 100% / 100% | 0–99 | 6d079b3bd6bc4947`
`P3 | make stealth-report | B0/B1/B2 rates for AT2 | 0% / 32% / 90%; B2 median delay 1165.5 s | 0–99 | 6d079b3bd6bc4947`
`P3 | make stealth-report | B0/B1/B2 rates for AT3 | 3% / 96% / 100% | 0–99 | 6d079b3bd6bc4947`
`P3 | make stealth-report | B0/B1/B2 rates for AT4 | 0% / 2% / 27% | 0–99 | 6d079b3bd6bc4947`
`P3 | make stealth-report | B0/B1/B2 rates for AT5 | 100% / 2% / 4% | 0–99 | 6d079b3bd6bc4947`
`P3 | make stealth-report | B0/B1/B2 rates for AT6 | 0% / 5% / 21% | 0–99 | 6d079b3bd6bc4947`
`P4 | make localization-report | threshold / dominance ratio | 3.8950 / 3.0 (threshold q99.5; ratio ties on tuning accuracy) | clean 0–99, tune 0–49 | 6d079b3bd6bc4947`
`P4 | make localization-report | AT1 temp localization | 100/100 correct | 0–99 | 6d079b3bd6bc4947`
`P4 | make localization-report | AT2 temp localization | 85/100 correct; 5 unknown; 10 none | 0–99 | 6d079b3bd6bc4947`
`P5 | make probe-report | combined validation false alarms | 0.19/h (600 clean windows) | 0–99 | 6d079b3bd6bc4947`
`P5 | make probe-report | AT3 V/I/combined detection | 100% / 100% / 100% | 0–99 | 6d079b3bd6bc4947`
`P5 | make probe-report | AT4 V/I/combined detection; B2 with probe | 0% / 3% / 3%; 29% | 0–99 | 6d079b3bd6bc4947`
`P5 | make probe-report | AT6 oracle V/I/combined detection | 0% / 3% / 3% | 0–99 | 6d079b3bd6bc4947`

## Ideas parked
- Remediate npm audit advisories in a dedicated dependency update with compatibility checks.

## Blockers / needs from user
- AT4 active verification limitation is documented above; P3 attack is frozen. P2 held-out false alarms are slightly above target and remain documented without retuning; NASA P1b remains unavailable and unsupported.
