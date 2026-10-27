# PROGRESS.md

Living log. Update after each task and phase so the current implementation state and evidence stay visible.

## Current status
- Current phase: P10 release hardening / deployment-readiness audit (P7 speed gate and P9 selected-site browser review remain open)
- Event clock at last update: 2026-10-27 (start time = 2026-10-26 00:00 local)
- Last green `make check`: 2026-10-26; current equivalent commands are being run individually because GNU Make is unavailable on this Windows host.
- Tags: none
- Continuation session: P0 and P1 are complete and pushed. P2 detector implementation, validation-only calibration, one-time held-out measurement, and diagnostic exports are complete.

## Current task plan — deployment-readiness audit and evidence
1. Preserve `static-website` as the primary frontend and leave simulation/API behavior intact unless a release blocker is demonstrated.
2. Reproduce measured-cell voltage validation and record dataset identity, split, metrics, and limitations.
3. Run the complete backend and static-site test, lint, type, and production-build gates; record warnings and failures.
4. Inspect the remaining P7–P11 requirements and execute safe software-only release checks where current workspace state permits.
5. Keep real-vehicle actions advisory; identify the HIL, pack, OEM/BMS, safety, and regulatory evidence that cannot be produced in this repository.
6. Update the checklist and this log with command-backed results; do not mark deployment readiness without physical integration evidence.

## Current task plan — frontend diagnostic label accuracy
1. Rename the response progression's shutdown label to identify simulated SAFE_MODE current limiting.
2. Relabel the client-derived temperature residual bar as a residual meter and avoid describing it as detector evidence.
3. Display localization confidence as a score, not as a percentage.
4. Keep the existing idle placeholders visible as waiting-state placeholders; do not change backend behavior or simulation data.
5. Run the existing static-site tests and production build, then record evidence in this log and the checklist.

## Frontend label corrections — 2026-10-27
- Replaced the visible “Shutdown” wording with “SAFE_MODE: current limited” and updated the matching response-state selector.
- Renamed the client-computed temperature residual bar to “Residual meter”; its accessible label now identifies its source. Classifier detail copy reports backend response state instead of implying that residual alone caused the state.
- Changed localization output from a percentage to a two-decimal heuristic score. Kept idle values unchanged; they remain waiting-state placeholders until a live or recorded frame arrives.
- Verification: `cd static-website && npm test` → 26 passed; `npm run build` passed (existing vendor-chunk advisory); `git diff --check` passed with existing LF/CRLF notices. Grep confirmed no visible “Shutdown”, “Strong residual”, or localization confidence-percent labels remain in the selected site. Backend files and behavior were not changed.

## Resume plan — baseline response recovery
1. Confirm the interrupted held-out evaluation left no complete result artifacts; do not reuse partial test-seed results. Confirmed: no result directory existed, and an attempted validation run through the test-labeled P7 CLI was stopped before output was produced.
2. Add deterministic recovery from SUSPECT after the configured number of clean challenge windows, resetting the count on renewed evidence.
3. Add focused response and baseline regression tests, then run relevant backend checks.
4. Re-run the defended baseline on validation seeds and inspect attack response regressions before accepting the behavior.
5. Freeze acceptance criteria before running held-out seeds 1000–1199; report the measured result without retuning.
6. Update readiness notes and checklist with evidence; leave physical deployment blocked pending real pack/HIL/OEM/safety validation.

## Resume execution — 2026-10-27
- Added SUSPECT recovery after `configs/default.yaml` `response.N_clean` consecutive clean challenge windows. New passive evidence, command tampering, or a failed probe resets the recovery count. CONFIRMED and SAFE_MODE behavior remains unchanged; SAFE_MODE still requires explicit operator reset.
- Added response regressions for the clean-window threshold, renewed-evidence reset, guard clamp vs command tampering, and seed 4242 honest baseline. Seed 4242 now ends NORMAL after `suspect_cleared`, never CONFIRMED/SAFE_MODE.
- Validation-only measurement: `backend/.venv/Scripts/python.exe scripts/validate_response_recovery.py --baseline-runs 100 --attack-runs 10 --workers 8`; baseline seeds 0–99 (100 one-hour runs) produced 13 B3 alarm episodes / 100 h = 0.13/h, below configured target 0.20/h; 13 runs entered SUSPECT, none entered CONFIRMED or SAFE_MODE, and none had hazards. Attack scenarios were sampled at seeds 0–9: AT1 10/10, AT2 8/10, AT3 10/10, AT4 1/10, AT5 10/10, AT6 0/10 detections. These are small validation samples, not general performance claims. Detailed per-run evidence: `data/results/p10_response_validation.json`.
- Updated P7 held-out evaluation completed on seeds 1000–1199 (1,400 scenario-seed runs, 12 workers) in 695.6 s. B3 baseline false alarms are 0.160/hour versus 0.135/hour for B2. B3 detects AT1 98.5%, AT2 81.0%, AT3 98.5%, AT4 19.5%, AT5 98.5%, and AT6 15.5%; B3 trails B2 on AT2, AT3, AT4, and AT6. Paired hazard rates improved AT2 0.5%→0%, AT3 28%→0%, AT5 97%→0%. No thresholds were tuned on test seeds. Full artifacts: `data/results/p10-response-recovery-heldout/`; current UI/API report files now point to these results under `data/results/`, with the previous report preserved in `data/results/p7-pre-response-recovery/`.
- The API smoke returned `/api/benchmarks` HTTP 200 with current config hash `f56e499aeb4d481e`, test seed bounds 1000–1199, and B3 baseline 0.16 episodes/hour. The dedicated endpoint contract test passed.
- Direct held-out baseline response-state audit (seeds 1000–1199, same config hash, 200 one-hour runs) found SUSPECT in 30 runs, `suspect_cleared` in 27, and zero CONFIRMED or SAFE_MODE runs. Three runs remained SUSPECT at the end; summary artifact: `data/results/p10_baseline_state_test.json`.
- Backend full pytest suite passed when rerun after the evaluation finished; an earlier concurrent run hit `BrokenProcessPool` in the repeatability test while the 12-worker evaluation was active. Targeted response/pipeline tests passed. Ruff and strict mypy passed from the backend project directory. Static-site Vitest 26/26, typecheck, and production build passed. The production build retains Vite's 513 kB vendor-chunk advisory. This static-site package does not define an `npm run lint` script.
- `git diff --check` passed (Git emitted only LF/CRLF working-copy notices). No commits were created because the overall workspace contains broad unrelated uncommitted changes and P10 is still incomplete.
- Readiness-record reconciliation: updated `docs/DEPLOYMENT_READINESS.md` to report the actual partial Chrome smoke (current benchmark data loaded; honest no-injection run later entered SUSPECT; wait timed out before recovery; no screenshot/console audit) instead of claiming browser access was unavailable. Updated the current backend suite count to 88 and linked the partial smoke from the P9 checklist. `git diff --check` passed again.

## Phase log
| Phase | Status | Budget | Used | Gate evidence | Notes |
|---|---|---|---|---|---|
| P0 Bootstrap | complete | 0.75 h | | `make setup && make check`; `make dev`; fresh source-copy setup/check; committed-tree `make check` | 14 backend tests and 1 frontend test passed at P0 completion; P0 reverified after push. |
| P1 Plant/twin | complete | 3 h | | `make check`; `make fit-twin`; `make plot-nominal`; user reviewed figure | 22 backend tests and 1 frontend test pass; all MUST criteria met. NASA P1b unavailable and unsupported. |
| P2 Passive detection | complete | 3.5 h | | `make check`; `make calibrate`; `make eval-passive` | Validation 0.1200 FA/h meets target; held-out test 0.2101 FA/h is reported above target without retuning. |
| P3 Attack engine | complete | 3 h | | `make check`; `make stealth-report`; `attacks-frozen` tag | AT1–AT6 and seven scenarios implemented; all SPEC 6 stealth criteria pass on validation seeds 0–99. |
| P4 Localization | complete | 2 h | | `make localization-report`; localization unit tests; `make check` | Validation threshold and dominance ratio calibrated; AT1 and AT2 confusion matrices recorded on seeds 0–99. |
| P5 Active verification | complete with AT4 limitation | 3.5 h | | `make probe-report`; probe tests; `make check` | Fresh keyed probes, safe amplitude clipping, gain detectors, validation calibration, sweep, overhead, and AT6 oracle results recorded. AT3 is exposed; active verification does not improve on B2 for AT4 and its reported-current input is the suspected cause. |
| P6 Guard/response | complete | 3 h | | `make guard-report`; response and guard tests; `make check` | Pessimistic command guard, virtual sensor, hysteretic response, and paired validation implemented. On seeds 0–9, AT3 hazard rate fell 30%→0 and AT5 100%→0; AT2/AT4 had no hazards in either arm. |
| P7 Evaluation | incomplete: runtime and B3-vs-B2 performance gate | 3 h | | Full 1,400-run evaluation, schema, repeatability | Updated run: 695.6 s on 12 workers; B3 detection trails B2 on AT2/AT3/AT4/AT6 |
| P8 API | complete | 3 h | | API/WebSocket tests; all scenarios at 60×; `make demo-data` | 79 backend tests, frontend tests/lint/typecheck/build green; seven 600-frame replay files generated locally with zero WebSocket errors. GNU Make is unavailable on this host, so targets were run directly. |
| P9 Frontend | in progress | 8 h | | Frontend quality checks; manual live and offline browser checks | Console shell, live telemetry, replay, scenario lab, benchmarks, and Method/limits views implemented. Remaining P9 requirements are listed in the checklist. |
| P10 Hardening | in progress | 4 h | | | |
| P11 Submission | todo | 3 h | | | |

## P8 completion evidence
- REST endpoints cover health, scenarios/story captions, bounded session lifecycle, real benchmarks, and threat model/limitations; malformed request bodies use the documented error envelope.
- WebSocket playback streams paired true state and counterfactual, estimates, evidence, response/localization, control, margins, and attack timing. Pause/resume, four speeds, seeded reset, validated injection, and SAFE_MODE operator-reset replay are supported; malformed messages return an error frame without closing the connection.
- Four concurrent 60× recordings completed in two waves across all seven scenarios. Every saved replay has 600 frames spanning simulated seconds 0–3599; the recorder aborts on any error frame.
- Full backend suite: 79 passed. Ruff and strict mypy passed; frontend Vitest, ESLint, TypeScript, and Vite build passed. The built app and health route returned HTTP 200.
- The user-selected primary frontend loads offline replay from `static-website/public/demo-runs/*.json`; `scripts/demo_data.py` / `make demo-data` now writes to that path. Include those replay assets in the release snapshot.

## P9 frontend work in progress
- Replaced the placeholder page with a responsive instrument-style console: paired protected/unprotected temperature traces, state and margin metrics, detector evidence, event list, seeded scenarios, playback speed, pause/resume, attack injection, and operator reset control.
- Added the API-backed scenario lab, benchmark results table with every detector/attack row and provenance, and Method/threat-model/limitations views. Benchmark failures and the 30.0-minute P7 evaluation runtime are visible in the UI.
- Browser smoke with the backend running verified `/api/scenarios`, a live WebSocket run, `/api/benchmarks`, and `/api/limits`. This exposed missing WebSocket support in the runtime dependencies; added `websockets` to `backend/pyproject.toml` and `backend/requirements.lock`, and enabled WebSocket forwarding in the Vite development proxy.
- Offline replay was opened in the browser after stopping the backend. The UI displayed the explicit recorded-replay banner and real recorded frames; starting a live run remained disabled.
- Verification: frontend TypeScript, ESLint, Vitest (1 passed), and production build passed. Backend pytest suite passed; Ruff and strict mypy passed across 35 source files.
- Still pending for P9: runtime validation/reconnect handling and shared state, dedicated channel-trust indicators, complete guided story/reproduction flow, benchmark plots and probe/localization details, Method equations, presentation-scale toggle, saved screenshots and user review, and broader UI tests.

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

## P6 implementation and evidence
- Added the 300-second pessimistic command guard with configured R_th, ambient, and R0 uncertainty, a closed-form horizon prediction equivalent to repeated twin steps, and an at-most-eight-step bisection for the largest safe current. SAFE_MODE uses the configured worst-case cooling resistance.
- Added the response state machine: one evidence class enters SUSPECT; two independent classes within 60 seconds, two consecutive failed probes, or an unsafe predicted command confirms; CONFIRMED persists for 10 seconds before SAFE_MODE. Exit requires an explicit operator reset and three clean challenge windows.
- Added virtual SOC/polarization/temperature estimates that fuse unflagged V/T channels. When no telemetry channel is trusted or SAFE_MODE forces isolation, the open-loop pessimistic twin supplies a degraded estimate. SAFE_MODE substitutes virtual temperature for charger derating and requests continuous keyed probes; probe current is clipped against next-step current, voltage, and thermal limits.
- `make guard-report` ran paired undefended/defended AT2, AT3, AT4, and AT5 scenarios on validation seeds 0–9 for 3600 seconds each. Peak temperature and voltage decreased in every paired defended run for all four attacks. Hazard-event rates were AT2 0%→0%, AT3 30%→0%, AT4 0%→0%, and AT5 100%→0%. Full paired per-seed metrics and event streams are in `data/results/p6_closed_loop_report.json`; the summary table is `data/results/p6_closed_loop_summary.md`.
- Full backend tests pass; Ruff and strict mypy pass; frontend test, lint, typecheck, and production build pass. Response tests cover confirmation hysteresis, two-probe confirmation, safe-mode persistence, operator reset, trust degradation/recovery, and the guard horizon against repeated twin simulation.

## P7 implementation and evidence
- Added deterministic multiprocessing evaluation over baseline and AT1–AT6 with per-run seed control, progress, detector metrics, Wilson intervals, false-alarm rate intervals, delays, safety margins, hazard changes, and localization confusion matrices. Reports include JSON, CSV, Markdown, metadata, and five SVG figures.
- The earlier test split used seeds 1000–1199, 200 runs per scenario, 3,600 seconds/run, and 12 workers; it took 1,802.4 seconds (30 minutes), missing the <10-minute gate. That report predates the response change and is preserved under `data/results/p7-pre-response-recovery/`.
- Updated held-out test split: same seeds/scenarios and 12 workers; 695.6 seconds, still above the 600-second gate. B3 baseline false alarms are 0.160/hour (target 0.20/hour; B2 is 0.135/hour). B3 detects AT1 98.5%, AT2 81.0%, AT3 98.5%, AT4 19.5%, AT5 98.5%, and AT6 15.5%; it trails B2 on AT2, AT3, AT4, and AT6. Updated UI/API report files are in `data/results/`, with full run details retained in `data/results/p10-response-recovery-heldout/`.
- Updated B3 paired hazard changes: AT2 0.5%→0%, AT3 28%→0%, AT5 97%→0%; no hazards occurred in either arm for the other scenarios. Do not generalize the 10-run validation attack measurements; the held-out per-scenario rates and confidence intervals are in `data/results/tables.md`. P7 runtime/performance limitations remain; S1 remains skipped.
- Reduced repeatability test passes; a regression test confirms test seeds 1000–1199 do not overlap calibration seeds 0–99. The report validates against its Pydantic schema. All 59 backend tests pass; Ruff and strict mypy pass. Code commits: `55db8e0` and `014acc3`; results/docs commit: `5cd5cdf`.
- Checklist correction: P5 and P6 evidence was recorded in the phase narrative, but the implementation checkboxes had remained unchecked. Both `PHASE_CHECKLIST.md` and the P5–P7 task lists in `PHASE_IMPLEMENTATION.md` now reflect verified evidence. The AT4 limitation and missed P7 runtime gate remain explicitly open.

## Exact continuation point
- P7's under-10-minute runtime criterion remains open. The current user-requested work is the deployment-readiness audit; measured-cell evidence has been added, but it reveals substantial held-out voltage-model error and is not pack or vehicle validation.
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
`P6 | make guard-report | AT3 hazard-event rate, undefended→defended | 30% → 0% | 0–9 | 6d079b3bd6bc4947`
`P6 | make guard-report | AT5 hazard-event rate, undefended→defended | 100% → 0% | 0–9 | 6d079b3bd6bc4947`

## Ideas parked
- Remediate npm audit advisories in a dedicated dependency update with compatibility checks.

## Blockers / needs from user
- AT4 active verification limitation is documented above; P3 attack is frozen. P2 held-out false alarms are slightly above target and remain documented without retuning; NASA P1b remains unavailable and unsupported.

### P9 cinematic story redesign update — 2026-10-27
- Kept `static-website/` as the primary UI and retained its Vite/TypeScript/Three.js implementation and existing FastAPI live-session wiring. No frontend framework migration or replacement was made.
- Reworked the page into a scroll-led scene: editorial opening, six staged narrative chapters, active live console, benchmark evidence, method/threat-model/limits, and research-prototype boundary. The vehicle scene responds to scroll and backend state; telemetry cards and the chart update from the active backend stream.
- Added backend-fed benchmark and limits sections, detail fields for live detector/control/localization evidence, responsive layouts, and an explicit recorded-run fallback when a live backend is unavailable. Replays use the checked-in static-website recordings and are labeled as recorded, not live.
- Visual inspection completed in the local browser at the opening, story, console, and research sections; the page is left open at the opening scene. API-backed scenario, benchmark, and limits content rendered from the running backend.
- Verification on 2026-10-27: `npm run build` passed; `npm test` passed (26 tests). `git diff --check` reported no whitespace errors; Git emitted line-ending conversion notices. Build retains the existing Three.js chunk-size warning.
- P9 remains in progress. Not completed here: full detector-by-attack benchmark plots and probe/localization breakdown, broader runtime validation/reconnect behavior, saved screenshot set/user review, and remaining quality gates in `PHASE_CHECKLIST.md`. Do not mark the phase complete or tag it yet.

### P9 dashboard simplification and Neo-Brutalist reskin — 2026-10-27
- Removed the seven scroll-narrative scenes and scroll-progress UI from `static-website`; the 3D camera no longer follows page scroll. It remains a subdued visual context and retains live incident focus.
- Re-centered the primary frontend on a stationary battery-analysis dashboard: live temperature chart, expanded classifier calculations, telemetry/control values, response posture, backend event log, and measured detector benchmark table. Added a collapsed backend-driven method/threat-model/limitations panel.
- Applied warm cream paper styling, dotted/stripe texture, yellow title sticker, bold black outlines and offset shadows, compact playful controls, restrained rotations, pink/cyan accents, and reduced-motion handling. Backend/API behavior and interaction handlers remain wired in place.
- Verification: `npm test` passed (26 tests); `npm run build` passed; `git diff --check` passed. The existing Three.js chunk-size advisory remains. Browser visual verification was unavailable on resume because local browser access was disabled in Work settings; do not claim a fresh screenshot review.

### Deployment-readiness audit — 2026-10-27
- Added a measured-data experiment using CALCE CS2_33. The workbook's cumulative discharge-capacity field is normalized per cycle; the experiment fits on 150 earlier cycles and holds out 248 later cycles. Training RMSE is 0.0563 V; later-cycle RMSE is 0.1916 V (MAE 0.1408 V; p95 absolute error 0.4069 V). This one-cell, capacity-referenced voltage fit does not validate temperature, pack behavior, attacks, BMS interfaces, or vehicle safety. Full method and archive hash: `docs/DATA_VALIDATION.md`; machine output: `data/results/calce_cs2_33_validation.json`.
- Verification on the current working tree: backend full pytest suite exited 0; Ruff passed; strict mypy passed for 36 source files; static-site Vitest passed (26 tests), TypeScript passed, and Vite production build passed. Vite still emits the existing >500 kB chunk warning. These checks validate software behavior only.
- P7 runtime gate remains missed: the earlier full run took 1,802.4 s, and the updated run took 695.6 s (target <600 s). The older alarm burden and seed-4242 false positive applied to the prior response implementation. Updated validation and held-out measurements are recorded above. `static-website/` remains the explicitly selected primary frontend; legacy React checklist items are not evidence for that site.
- Original root-cause trace: seed 4242 had one B2 alarm at 218 s (true temperature 39.44 °C). At 499 s the normal 90 A request was clamped to 63.83 A by the 300 s pessimistic command guard (true temperature 43.02 °C), but this expected intervention was treated as malicious-command evidence. The current code separates these paths; validation seed 4242 returns to NORMAL after clean challenges, and updated held-out metrics are recorded above.
- Frontend toolchain was upgraded to Vite 8 / Vitest 4 after the npm advisory scan found six issues, including two critical. `npm audit fix` then reported zero vulnerabilities; frontend tests (26), typecheck, and build passed. Build still warns about the 599.03 kB JavaScript chunk (155.29 kB gzip).
- Fixed API readiness reporting: `/api/health` now loads the calibrated detection file and checks its config hash/metadata; session creation returns 503 when it is missing or invalid. The primary UI falls back to recorded replay with a calibration-specific status. Added regression checks for missing calibration and missing benchmark outputs. Added explicit limits for demo-only probe keys, alert transport, authentication, and TLS.
- Backend dependency audit was attempted with `pip-audit` against the locked requirements, but the vulnerability-service query stalled and was interrupted; no clean Python dependency-audit result is available.
- P10/P11 remain incomplete: no clean committed snapshot for fresh-clone verification, no defined memory/RSS acceptance threshold, no Playwright smoke, no complete release packaging/user review, and no final claim review. The three-pass soak has since completed: all seven scenarios × three rounds, 21 sessions, 600 frames each, zero stream-error assertions; `tracemalloc` current growth 4,456,522 bytes and peak growth 10,008,749 bytes (Python allocations only, no pass/fail limit). Physical deployment remains out of scope without a specified BMS, real data, HIL/pack test rig, OEM integration authority, and independent functional-safety/cybersecurity approval.
- Final selected static frontend checks after the Vite 8 bundle configuration: `npm test` 26/26, `npm run typecheck`, production build, and `npm audit --audit-level=moderate` all pass (0 vulnerabilities). Build now emits ~513 kB vendor JS and ~63 kB app JS, with the >500 kB vendor advisory still present. `git diff --check` passes; only line-ending conversion notices were emitted. Browser visual review remains unavailable in this app session.
- After adding real-file API fault cases, full backend pytest passes (87 tests), Ruff passes, and strict mypy passes (36 source files). Missing/malformed/un-calibrated `detection.yaml` makes health degraded and blocks sessions; missing benchmark files returns 404 and corrupt JSON returns 503. A live Uvicorn/WebSocket drill received the first baseline frame, then verified process termination closes the stream (code 1006). This does not verify the browser's user-facing recovery, so end-to-end failure/recovery remains open.
- Added repeatable `scripts/failure_drill.py` and `make failure-drill` for backend process termination during a live WebSocket; the script passed twice and prints the boundary of what it verifies. The Python audit retry (`pip-audit --timeout 10`) still stalled against the vulnerability service and was interrupted; Python dependency risk remains unaudited.
- Extended measured-cell validation with a physical-cell holdout: fitted on 150 early CS2_33 cycles and evaluated all 775 cycles from the separate CS2_34 cell. Cross-cell RMSE is 0.0919 V, MAE 0.0691 V, p95 absolute error 0.1761 V over 77,435 decimated samples. The official archive SHA-256s, protocol, method, and limitations are documented in `docs/DATA_VALIDATION.md`; raw data remain ignored and are not committed. This is still lab-cell electrical-model evidence, not pack/vehicle or safety validation.
- Added checksum-pinned public-data retrieval (`scripts/download_calce.py`, `make download-calce`) with path-safe extraction. Re-ran it successfully for CS2_33 and CS2_34; hashes matched and the CS2_34 archive yielded 23 workbooks. New regression covers CALCE cell-specific worksheet suffixes. Full backend pytest now passes 88 tests; Ruff passes on backend and new scripts; strict mypy passes for backend source.

### User-requested Aurora Bento redesign — 2026-10-27
1. Preserve the existing static-website frontend, its content, backend connections, and interactions.
2. Translate the requested off-white, dotted-grid, lime accent, glass and aurora palette into CSS tokens.
3. Restyle the existing dashboard into asymmetrical bento panels without changing its data or controls.
4. Keep the battery scene subdued behind the dashboard and preserve responsive behavior.
5. Add bundled Manrope typography if it fits the existing offline frontend setup.
6. Run the static-website production build and tests; inspect the resulting diff for frontend-only scope.
7. Record the change and evidence in the P9 log without marking the overall phase complete.

### P9 Aurora Bento visual redesign — 2026-10-27
- Re-skinned the existing `static-website/` dashboard using an off-white dotted canvas, softly translucent surfaces, restrained lime status accents, and the specified green, amber, and coral/blue aurora gradient families. Restyled its existing controls, telemetry cards, chart surface, response steps, benchmark table, dialogs, and mobile layout without changing application content or event behavior.
- Added bundled Manrope weights 300/400/500 for offline use. The live Three.js vehicle visual remains behind the dashboard with a soft fade mask.
- Frontend-only files changed for this request: `static-website/src/style.css`, `static-website/src/main.ts`, and the static-site package manifest/lock; backend architecture was not changed. Existing unrelated working-tree edits were left untouched.
- Verification: `npm run build` passed; `npm test` passed (26 tests); `git diff --check` passed. The existing Vite warning about a 598.90 kB JavaScript chunk remains. Final browser refresh was interrupted by a physical Escape key, so manual visual verification is still pending.
- P9 remains in progress; this visual pass does not complete the phase or its broader acceptance criteria.

### User-requested dark Glassmorphism Command Center redesign — 2026-10-27
1. Keep the selected `static-website/` app and preserve all existing content, controls, and live-data wiring.
2. Use the provided aerial road screenshot as composition reference; do not embed its visible stock-photo watermarks.
3. Create an original offline vector road backdrop with forest texture, central route, waypoints, and vehicle highlight.
4. Re-skin the header, controls, telemetry, response, event log, benchmark, and method panels in dark glass styling.
5. Reflow existing content into left, center, and right dashboard columns, then stack cleanly for tablet and mobile.
6. Reuse only live or existing measured values; skip the pasted brief's sample trip, speed, range, and efficiency figures.
7. Run static-site tests and production build; record results without changing backend architecture or claiming P9 complete.

### Revert latest command-center layout correction — 2026-10-27
- At the user's request, removed the latest top navigation, live callouts, paired chart, brightened background treatment, and command-center reflow. Kept the earlier dark glass dashboard design and existing run/control/data flow.
- Verification after revert: `cd static-website && npm run build` passed; `npm test` passed (26 tests); `git diff --check` passed. Vite still reports the existing 513.24 kB vendor chunk advisory.
- Backend files and architecture were not changed for this revert. P9 remains in progress.

### User-pasted dark Command Center brief — 2026-10-27
1. Recheck the existing static-site layout and use the newly supplied dark command-center brief as the current visual target.
2. Preserve every existing backend connection, selector, attack control, chart, benchmark, and detail section.
3. Build the fixed road-and-car composition using the bundled offline visual and percent-positioned route/ring elements.
4. Arrange current dashboard content into compact left, open center, right, and lower regions without adding unmeasured dashboard statistics.
5. Add navigation and vehicle callouts only where they point to existing sections and live sample fields.
6. Keep the dark glass palette, reduced-motion behavior, and narrow-screen scroll layout.
7. Verify the static-site build/tests and document the visual decision and result; leave backend files untouched.
- Applied the current dark brief to the selected static site: used the provided road image as the full-viewport background, added the centered route/ring, top section navigation, live-value callouts, and desktop left/center/right composition with a responsive stacked layout. Existing controls, event stream, temperature chart, benchmarks, and method details remain connected.
- Data decision: did not add the sample trip counts, efficiency, speed, range, or alert totals from the brief; callouts use current true temperature, SOC, and current samples and show `--` before telemetry. The provided screenshot is bundled locally as `static-website/public/images/road-aerial.png` for offline use and contains visible stock-photo watermarks.
- Verification: static-site `npm run build` passed; `npm test` passed (26 tests); `git diff --check` passed. The existing Vite vendor-chunk advisory remains. Browser preview was available only at a 600 px viewport, so desktop-scale visual QA remains pending.
- No backend files or architecture were changed. P9 remains in progress.

### User-requested command-center alignment pass — 2026-10-27
1. Inspect the current static-site dashboard at desktop and narrow widths and identify layout collisions or awkward spacing.
2. Fix alignment and panel placement using CSS Grid and responsive rules; preserve all existing sections and controls.
3. Keep the car route unobstructed and retain live callouts, road background, glass styling, and honest empty values.
4. Make the desktop view fit cleanly while keeping the tablet/mobile stack readable and scrollable.
5. Run the static-site production build and existing tests, then record evidence without touching backend files.
- Desktop alignment pass: removed inherited fixed-height/overflow behavior from the vehicle and scenario control card; placed the classifier below it; separated response posture and backend events into a right-side stack; reduced classifier spacing to fit without sideways scroll; assigned an explicit order for the responsive layout. Existing CSS remains the only UI change in this pass.
- Verification: `cd static-website && npm run build` passed; `npm test` passed (26 tests); `git diff --check` passed. Browser UI access was disabled during this pass, so visual screenshot confirmation remains pending; earlier 600 px preview indicated mobile content flow needs visual review when browser access is available. Existing Vite vendor-chunk advisory remains.
- No backend files changed. P9 remains in progress.

### User-requested scroll/module visibility correction — 2026-10-27
1. Inspect the fixed desktop rails and the document sections below the command-center viewport.
2. Keep vehicle/scenario and classifier controls available during the command-center view without allowing them to cover later sections.
3. Keep response posture and backend events aligned with the command-center view, then clear them from the way when scrolling into other sections.
4. Preserve responsive mobile flow and all simulation interactions.
5. Run static-site build/tests and record the result; no backend changes.
- Added a desktop-only visibility boundary for the floating command-center rails: they stay available while the central live chart is in view and fade out before the user scrolls into benchmark/method content. Responsive layouts continue to use normal document flow. This prevents fixed controls and event panels from sitting over lower-page sections.
- Verification: `cd static-website && npm run build` passed; `npm test` passed (26 tests); `git diff --check` passed. Vite retains its existing vendor-chunk advisory. Browser access was unavailable for a fresh visual scroll capture.
- No backend files changed. P9 remains in progress.

### User clarification: position panels only — 2026-10-27
1. Remove the unrequested scroll-triggered visibility behavior.
2. Keep the vehicle/scenario controls and classifier aligned as the left rail.
3. Keep response posture and backend events aligned as the right rail, with the live chart centered.
4. Preserve the responsive stacked layout and all existing controls/data flow.
5. Verify with the static-site build/tests and leave backend files untouched.
- Removed the scroll-triggered rail hiding added in the prior pass. Desktop controls/classifier remain anchored to the left; response/events remain anchored to the right; responsive breakpoints still return these panels to normal flow.
- Verification: static-site `npm run build` passed, `npm test` passed (26 tests), and `git diff --check` passed. No backend files changed.

### User request: rebuild the command-center layout — 2026-10-27
1. Rebuild the frontend page structure into explicit header, left rail, center dashboard, and right rail containers.
2. Put existing run controls and classifier together; put existing response and event modules together.
3. Keep the road/car/callouts anchored to the viewport and place the live chart in the center column.
4. Use sticky rails within the page grid so scrolling content cannot cause overlay collisions.
5. Preserve all IDs, controls, live data wiring, benchmark/method sections, and mobile scrolling.
6. Verify static-site build/tests and document results; do not change backend architecture.

### User request: final alignment cleanup — 2026-10-27
1. Audit the rebuilt grid for cascade and responsive breakpoint conflicts.
2. Correct the tablet/mobile center-column placement so it follows the one- and two-column grids.
3. Keep panel edges, gutters, and sticky rail heights consistent.
4. Run static-site build/tests and record evidence; preserve backend behavior.

### User request: final visual polish — 2026-10-27
1. Review current command-center grid, scroll behavior, and responsive CSS for remaining alignment/overflow issues.
2. Apply a final frontend-only spacing and typography cleanup without changing sections, controls, or live data.
3. Check desktop and narrow viewport behavior where tooling allows.
4. Run the static-site build/tests and record evidence; leave backend files untouched.
- Corrected the breakpoint selector specificity so the center dashboard stays in column two on tablet and moves to the single-column row on mobile. The explicit rail wrappers keep the left controls/classifier and right response/events aligned to the same top and bottom edges; the center remains independently sized between them.
- Verification: `cd static-website && npm run build` passed; `npm test` passed (26 tests); static HTML ID check found no duplicates; `git diff --check` passed. Browser screenshot inspection was unavailable in this turn; no backend files changed.
- Rebuilt the page structure into explicit left and right sticky rails around the center dashboard. Vehicle/scenario/run controls and the classifier now share one left column; response posture and backend events share one right column; the title, temperature chart, and evidence sections occupy the center column. Responsive breakpoints switch to two columns and then a single scrollable stack.
- Preserved the existing DOM IDs and controls; verified no duplicate IDs. No simulation/API/ backend code was modified.
- Verification: `cd static-website && npm run build` passed; `npm test` passed (26 tests); `git diff --check` passed. The existing Vite vendor chunk-size advisory remains. Browser visual inspection was unavailable in this turn.
- P9 remains in progress.

### User request: final alignment and presentation pass — 2026-10-27
1. Separate the live hero dashboard from the lower evidence and reference sections within the command grid.
2. Give the three desktop columns consistent top alignment, gutters, and viewport fit.
3. Set deliberate tablet and mobile flow so none of the panels collide or overlap.
4. Preserve all current content, IDs, controls, and live data wiring; frontend only.
5. Run the static-site build and tests, then record evidence in the checklist and progress log.

- Separated the live hero/chart from evidence, benchmark, and method panels so the left controls, center view, and right response/events align in a single viewport-height row. The lower sections now follow under the center column. Reduced the post-header gap and removed extra title top padding so the eyebrow/title aligns with the panels. Tablet and mobile retain a clean stacked flow. Preserved IDs, backend-driven data, and controls; no backend files changed.
- Verification: `cd static-website && npm run build` passed; `npm test` passed (26 tests); `git diff --check` passed. Vite still reports the existing vendor chunk-size advisory. Browser visual confirmation remains pending.

### User clarification: alignment still needs work — 2026-10-27
1. Recheck the active static-site layout rules and responsive grid overrides.
2. Align the title edge, chart, left rail, and right rail to one shared grid and consistent gutters.
3. Remove conflicting layout declarations that cause uneven spacing across breakpoints.
4. Preserve all content, controls, and backend data wiring; make frontend-only changes.
5. Verify the static-site build and tests; record evidence without changing backend architecture.
- Replaced the previous layout overrides with one concise grid definition: matching column gutters, a title aligned to the chart edge, and dedicated tablet/mobile placements. Kept all controls, content, and backend wiring intact.
- Verification: `cd static-website && npm run build` passed; `npm test` passed (26 tests). The build retains the existing vendor chunk-size advisory. No backend files changed.
