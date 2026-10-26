# PHASE_CHECKLIST.md

Tick `[x]` only with an evidence note: `- [x] item — evidence: <command> → <result>`.
Unticked items at a phase gate block the phase unless a cut is logged in PROGRESS.md.

## P0 Bootstrap
- [x] Clean source copy: `make setup && make check` passes — evidence: fresh copy excluding `.git`, environments, dependencies, and build outputs → backend 14 passed; frontend 1 passed; Ruff, strict mypy, ESLint, TypeScript, and production build passed
- [x] `make dev` starts backend (:8000) and frontend (:5173); `/api/health` returns JSON — evidence: live run returned health 200 and Vite ready; Ctrl+C shut down Uvicorn and no listeners remained
- [x] All Makefile targets from CLAUDE.md exist (stubs allowed only for later phases, and fail loudly with "not implemented in this phase") — evidence: Makefile targets reviewed; `make calibrate` reports `not implemented in this phase: calibrate`
- [x] `configs/default.yaml` loads through pydantic; config hash printed at startup — evidence: health test passes with lifespan and config-hash assertion; live startup logged hash `87950a9351118e47`
- [x] Fonts bundled locally (no network request to font CDNs) — evidence: `cd frontend && npm run build` → IBM Plex font files emitted under `dist/assets/`

## P1 Plant, twin, sensors, charger
- [x] Determinism test: same seed twice gives identical arrays — evidence: `test_pipeline_is_deterministic_for_a_seed` → all trajectory arrays exactly equal
- [x] SOC monotone and charge-conserving test — evidence: `test_plant_advance_conserves_charge_and_is_seed_reproducible` → SOC increment matches η·I·t/(3600·Q), monotone
- [x] Analytic steady-state thermal test within 1% — evidence: `test_plant_thermal_steady_state_matches_analytic_solution` → within 1%
- [x] Honest run: T_true < T_warn, V within limits (SPEC 2 target 1) — evidence: `make plot-nominal` → peak T 45.98 °C, peak V 4.1937 V, final SOC 0.9444
- [x] Under-reported T run reaches T_hazard within about 25 min (SPEC 2 target 2) — evidence: `make plot-nominal` → crosses 55 °C at 23.10 min while T_rep is held at 30 °C
- [x] Hijacked 150 A request in CV phase reaches V or SOC hazard within 5 min — evidence: `make plot-nominal` → first CV hijack at 54.67 min, voltage hazard after 141 s
- [x] No NaN across 200 random seeded configs — evidence: `test_two_hundred_varied_units_have_finite_trajectories` → all trajectory values finite
- [x] Twin parameters fitted on validation data and recorded in config — evidence: `make fit-twin` / `scripts/fit_twin.py --seed 10000 --write` → R1_n 0.001083371522 Ω, tau1_n 55.23743011 s, polarization RMSE 0.00228423 V
- [x] Plausibility figure produced and shown to user — evidence: `make plot-nominal` → `docs/screens/p1-plausibility.png` shown in phase report
- [x] (COULD) P1b NASA validation script ran, with RMSE on held-out cycles, or "dataset unavailable" logged — evidence: `data/raw/nasa/` absent → dataset unavailable; claim marked unsupported, no dataset scraped

## P2 Passive detection
- [x] EKF NIS/NEES test on a synthetic linear system passes — evidence: `test_ekf_nis_and_nees_are_consistent_on_a_synthetic_linear_system` → means 1.998 (2 dof) and 2.883 (3 dof), both within 99% chi-square bounds
- [x] Singular covariance raises `NumericalError` (test) — evidence: `test_ekf_singular_innovation_covariance_raises_typed_error` passes
- [x] CUSUM and NIS window unit tests (known inputs, known alarm times) — evidence: `test_detectors.py` → NIS alarms on sample 3; two-sided CUSUM alarms on sample 2 and resets
- [x] `make calibrate` writes `configs/detection.yaml` with metadata from validation seeds only — evidence: seeds 0–99, config hash `6d079b3bd6bc4947`, date `2026-10-26`
- [x] Combined passive FA/hour on validation recorded — evidence: `data/results/passive_fa_validation.json` → 12 episodes / 99.97 h = 0.1200/h (target 0.20/h)
- [x] FA/hour on test attack-free seeds measured once; value logged in PROGRESS.md — evidence: `data/results/passive_fa_test.json`, frozen thresholds, seeds 100–199 → 21 episodes / 99.97 h = 0.2101/h
- [x] NIS QQ diagnostic data exported — evidence: `data/results/nis_qq.json` → observed validation quantiles and chi-square df=2 comparison

## P3 Attack engine
- [x] AT1–AT6 implemented with documented knowledge level — evidence: `configs/attacks.yaml`, `backend/src/physiguard/attacks/`
- [x] AT4 test: never reads probe or `I_cmd` (enforced by interface, not convention) — evidence: separate `AttackContext` and `TruthState` types plus forbidden-field test
- [x] AT1–AT5 outputs within static range limits where specified (test) — evidence: `backend/tests/test_attacks.py`; AT1 spikes are intentionally allowed to cross the B0 temperature limit and AT5 can create honest overvoltage
- [x] Hazard reachable undefended — evidence: existing under-reported-temperature and 150 A CV hazard tests in `backend/tests/test_pipeline.py`, plus AT5 attack-run hazard test
- [x] Stealth report: B0/B1/B2 detection rates per attack printed — evidence: `make stealth-report`, `data/results/stealth_report.json`, validation seeds 0–99
- [x] SPEC 6 stealth requirements satisfied; AT4 attack model fixed and logged — evidence: AT4 B2 catch rate 27% (≤90%), AT2 B1 32% vs B2 90%, AT1 B2 100%
- [x] `configs/attacks.yaml` frozen; tag `attacks-frozen` created — phase-gate commit/tag
- [x] `configs/scenarios.yaml` includes `story_ladder`

## P4 Localization
- [ ] Single-channel fault unit tests pass
- [ ] Confusion matrix on validation for AT1 and AT2
- [ ] `multi` / `command` / `unknown` outputs covered by tests (or cut logged)

## P5 Active verification
- [ ] Probe zero-mean, within limits, deterministic given key+nonce, differs across nonces (tests)
- [ ] Authentic telemetry gives gain near 1 on validation windows
- [ ] AT3/AT4 gain near 0 on validation; replay of old probe fails (tests)
- [ ] `g_min` calibrated on validation attack-free windows
- [ ] V-only, I-only, combined results reported separately
- [ ] Detection vs probe amplitude sweep generated
- [ ] Probe overhead (heating, charge time, efficiency) measured
- [ ] AT6 oracle result generated and labelled as a limit

## P6 Command guard and response
- [ ] Guard clamps unsafe request (AT5) in closed loop (test)
- [ ] State machine: hysteresis, no flapping, operator reset (tests)
- [ ] Virtual sensor marked `degraded` when all telemetry is suspect
- [ ] Paired plants deterministic (same seed, same attack)
- [ ] Defended vs undefended hazard table on validation printed

## P7 Evaluation harness
- [ ] `make eval` finishes < 10 min
- [ ] `results.json` validates against schema; CSV, tables, figures, meta written
- [ ] Repeatability test: two runs, identical results
- [ ] No test seed used in calibration (assertion in code)
- [ ] Failures (scenarios where B3 does not help) present in results, not filtered
- [ ] Results committed to `data/results/`

## P8 API and sessions
- [ ] REST validation and error shape tests
- [ ] WebSocket protocol tests including malformed messages
- [ ] Inject mid-run reproducible (same seed + same inject time gives identical frames)
- [ ] 4 concurrent sessions OK; 5th rejected with clear error
- [ ] Idle sessions cleaned up
- [ ] Scripted client runs all scenarios at 60× with zero errors
- [ ] `/api/benchmarks` and `/api/limits` serve real content
- [ ] `make demo-data` recorded all scenarios

## P9 Frontend
- [ ] 9a: tokens, shell, API client, WS hook with backoff, store, error boundary
- [ ] 9a: offline replay mode works with backend stopped, banner visible
- [ ] 9b: console shows protected vs unprotected true temperature, reported, predicted, limits, attack window
- [ ] 9b: evidence strip, state indicator, channel trust, event timeline, controls, injection dock
- [ ] 9c: guided `story_ladder` runs end-to-end with captions
- [ ] 9d: Benchmarks renders real `results.json`, failures shown with equal prominence
- [ ] 9e: Method and limits view content from `/api/limits`
- [ ] 9f: keyboard navigation and visible focus; reduced motion; presentation-scale toggle
- [ ] Loading, empty and error states exist for every data-driven view
- [ ] No console errors/warnings during the DEMO_SCRIPT walkthrough
- [ ] `tsc --noEmit`, ESLint, Vitest, production build all pass
- [ ] Screenshots in `docs/screens/` reviewed by user

## P10 Release hardening
- [ ] Fresh-clone script passes end to end
- [ ] Soak test: all scenarios × 3 at 60× with zero error frames
- [ ] Failure drills pass: backend killed mid-run, bad config, missing detection.yaml, missing results.json
- [ ] Playwright smoke passes (SHOULD)
- [ ] README complete; no TODO/FIXME/commented-out code (grep check)
- [ ] `make check` has zero warnings
- [ ] Offline test: disable network, `make serve`, full demo works
- [ ] Tag `v1.0.0`

## P11 Submission
- [ ] CLAIMS_EVIDENCE rows all `supported`, `softened`, or `removed`, with file paths
- [ ] Final form text updated to match evidence
- [ ] Tech stack text matches what is installed (no `filterpy`; scikit-learn only if S1 shipped)
- [ ] Backup demo video recorded
- [ ] Demo machine: `v1.0.0` checked out, `make serve` verified offline, browser zoom and presentation mode tested on the projector resolution
- [ ] Q&A sheet reviewed by presenter

## Release criteria (all must be true)
- [ ] Every number on screen is traceable to `results.json` or a live run
- [ ] Limits view lists A2 oracle failure and out-of-scope items
- [ ] No claim of certification, real-hardware validation, or deployment readiness anywhere
