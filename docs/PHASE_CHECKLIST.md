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
- [x] (COULD) P1b NASA validation script ran, with RMSE on held-out cycles, or "dataset unavailable" logged — evidence: `data/raw/nasa/` absent at P1b; NASA claim was marked unsupported then. A later, separate CALCE experiment is recorded below; NASA validation remains unavailable.

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
- [x] Single-channel fault unit tests pass — evidence: synthetic voltage-only and temperature-only steps through the EKF bank
- [x] Confusion matrix on validation for AT1 and AT2 — evidence: `data/results/localization_report.json`, seeds 0–99
- [x] `multi` / `command` / `unknown` outputs covered by tests (or cut logged) — evidence: `backend/tests/test_localize.py`; SPEC multi scoring implemented in `eval/metrics.py`

## P5 Active verification
- [x] Probe is zero-mean, within limits, deterministic for key+nonce, and differs across nonces — probe tests pass
- [x] Authentic telemetry gives gain near 1 on validation windows — `data/results/probe_report.json`
- [x] AT3 near-zero gain and stale-probe replay rejection verified; AT4 near-zero target was not achieved and is documented as a frozen-attacker observability limitation — `data/results/probe_report.json`
- [x] `g_min` calibrated on validation attack-free windows — 600 windows, seeds 0–99
- [x] V-only, I-only, and combined results reported separately — `data/results/probe_report.json`
- [x] Detection versus probe-amplitude sweep generated — `data/results/probe_amplitude_sweep.svg`
- [x] Probe overhead (heating, charge time, efficiency) measured — 20 paired validation runs
- [x] AT6 oracle result generated and labelled as a limit — `data/results/probe_report.json`

## P6 Command guard and response
- [x] Guard clamps unsafe request (AT5) in closed loop — response and pipeline tests pass
- [x] State machine hysteresis, persistence, and operator reset covered — `backend/tests/test_response.py`
- [x] Virtual sensor is marked degraded when telemetry is untrusted — `backend/tests/test_response.py`
- [x] Paired plants use matching seeds and attack inputs — `backend/tests/test_pipeline.py`
- [x] Defended versus undefended hazard table printed for validation seeds 0–9 — `data/results/p6_closed_loop_summary.md`

## P7 Evaluation harness
- [ ] Evaluation finishes < 10 min — **missed:** updated full run took 695.6 s for 1,400 hourly scenario-seed runs on 12 workers (previous run: 1,802.4 s)
- [x] `results.json` validates against schema; CSV, tables, figures, and metadata written — `data/results/`
- [x] Repeatability test: reduced evaluation run twice, identical JSON
- [x] Held-out seeds 1000–1199 do not overlap calibration seeds 0–99 — regression test
- [x] Failures and limits stay in results — updated B3 baseline FA 0.160/hour; AT4 B3 detection 19.5%, AT6 15.5%; B3 trails B2 on AT2/AT3/AT4/AT6; AT5 detection 98.5%. Current report: `data/results/results.json`; prior report preserved at `data/results/p7-pre-response-recovery/`.
- [ ] Updated results committed to `data/results/` — working tree is broadly dirty and no commit was made during this task.

## P8 API and sessions
- [x] REST validation and error shape tests — `backend/tests/test_api.py`
- [x] WebSocket protocol tests including malformed messages that keep the connection open — `backend/tests/test_api.py`
- [x] Inject mid-run reproducible (same seed + same inject time gives identical frames) — `backend/tests/test_api.py`
- [x] Four concurrent sessions accepted; fifth rejected with a clear error — `backend/tests/test_api.py`; all-scenario 60× recorder ran four sessions concurrently
- [x] Idle sessions cleaned up — 15-minute expiry covered by `backend/tests/test_api.py` and the app cleanup loop
- [x] Scripted client runs all scenarios at 60× with zero errors — `scripts/demo_data.py`; seven scenarios completed with 600 frames each
- [x] `/api/benchmarks` and `/api/limits` serve real content — `backend/tests/test_api.py`
- [x] `make demo-data` records all scenarios — target implemented; on this Windows host the script was run directly because GNU Make is unavailable; generated offline replay files belong in `static-website/public/demo-runs/` for the user-selected primary frontend and must be included in the release snapshot.

## P9 Frontend (original React checklist; superseded by user-approved static frontend)
- [x] Console shell, local typography, status bar, and responsive navigation implemented — evidence: browser preview at the in-app browser's 600 px viewport; narrow layout showed icon navigation; IBM Plex fonts loaded locally
- [x] Recorded replay works with backend stopped and labels data as recorded — evidence: browser smoke after stopping Uvicorn → offline scenario catalog remained available, and “Recorded replay. This is not a live simulation.” with 600 frames displayed
- [x] Live paired temperature trace, simulated limit, state, margins, evidence metrics, and event list render streamed WebSocket data — evidence: browser smoke with model_synthesis → live frames and detector values updated
- [x] Scenario catalog and story captions load from `/api/scenarios` — evidence: Lab view displayed all seven configured scenarios and captions
- [ ] 9a: tokens, shell, API client, WS hook with backoff, store, error boundary
- [x] 9a: offline replay mode works with backend stopped, banner visible — evidence: backend stopped in browser smoke; offline catalog remained available and replay showed its banner plus recorded frames
- [ ] 9b: console shows protected vs unprotected true temperature, reported, predicted, limits, attack window
- [ ] 9b: evidence strip, state indicator, channel trust, event timeline, controls, injection dock
- [ ] 9c: guided `story_ladder` runs end-to-end with captions
- [x] 9d: Benchmarks renders real `results.json`, failures shown with equal prominence — evidence: browser view showed all seven scenarios, B0–B3, seed/provenance, false-alarm/hazard outcomes, and the missed runtime gate
- [x] 9e: Method and limits view content from `/api/limits` — evidence: browser Method view displayed API-provided methods, assets, capabilities, out-of-scope items, and limitations
- [ ] 9f: keyboard navigation and visible focus; reduced motion; presentation-scale toggle
- [x] User-requested Aurora Bento visual reskin applied to the selected static site — evidence: `cd static-website && npm run build` passed; `npm test` → 26 passed; `git diff --check` passed. Full browser screenshot review remains pending.
- [x] User-pasted dark Command Center visual pass applied to the selected static site — evidence: `cd static-website && npm run build` passed; `npm test` → 26 passed; `git diff --check` passed; 600 px browser preview showed responsive controls, nav, and live callout placeholders. Desktop-scale visual QA remains pending.
- [x] User-requested command-center alignment fixes — evidence: `cd static-website && npm run build` passed; `npm test` → 26 passed; `git diff --check` passed. Updated fixed desktop control/classifier and response/event rails plus responsive order; a later fresh Chrome live smoke is recorded below, while full browser visual and accessibility review remains open.
- [x] Fixed command-center rails no longer obscure lower scrolling sections — evidence: `cd static-website && npm run build` passed; `npm test` → 26 passed; `git diff --check` passed. Desktop-only visibility is tied to the live chart viewport; mobile/tablet remain in normal flow. Browser scroll screenshot unavailable.
- [x] Reverted unrequested scroll-triggered rail hiding per user clarification — evidence: static-site build passed; 26 tests passed; `git diff --check` passed. Desktop side rails stay fixed; tablet/mobile use normal flow.
- [x] Rebuilt command-center page into explicit aligned rails and center column — evidence: `cd static-website && npm run build` passed; `npm test` → 26 passed; `git diff --check` passed; checked static HTML IDs are unique. Desktop browser screenshot review remains pending.
- [x] Responsive grid alignment cleanup — evidence: static-site build passed; 26 tests passed; no duplicate HTML IDs; `git diff --check` passed. Corrected the high-specificity center grid placement at tablet/mobile breakpoints.
- [x] Final presentation cleanup — evidence: `cd static-website && npm run build` passed; `npm test` → 26 passed. Standardized desktop grid columns/gutters and aligned the title edge with the chart; tablet/mobile retain explicit stacked order.
- [ ] Loading, empty and error states exist for every data-driven view
- [ ] No console errors/warnings during the DEMO_SCRIPT walkthrough
- [x] `tsc --noEmit`, ESLint, Vitest, production build all pass — evidence: `npm run typecheck`, `npm run lint`, `npm test` → 1 passed, `npm run build` → 173.83 kB JS (54.83 kB gzip); full P9 gate still waits on remaining P9 items
- [ ] Screenshots in `docs/screens/` reviewed by user

Selected `static-website/` verification on 2026-10-27:
- [x] Dashboard's API data routes and primary static build mounted together — evidence: FastAPI `TestClient` against built site; `/` = 200, `/api/health` = ok, `/api/scenarios` = 7, `/api/benchmarks` = 200, `/api/limits` = 200.
- [x] Static-site tests, TypeScript, production build — evidence: Vitest 26 passed; `npm run typecheck` passed; `npm run build` passed. Current split is ~513 kB vendor JS plus ~63 kB app JS; Vite still reports the vendor chunk advisory.
- [x] Frontend dependency audit — evidence: `npm audit --audit-level=moderate` after non-breaking `npm audit fix` → 0 vulnerabilities.
- [ ] Browser-level incident recovery, accessibility, console-error, and offline network-disabled walkthrough — partial smoke below; remaining checks are not covered by unit/API tests.
- [x] Fresh Chrome smoke: dashboard loaded current `/api/benchmarks` data (config `f56e499aeb4d481e`, seeds 1000–1199, B3 baseline 0.160/hour); honest baseline streamed live telemetry with no injection and raised SUSPECT by simulated 09:19; the in-vehicle preview said the alert alone does not prove malware. The live run wait timed out before clean-challenge recovery could be confirmed. No screenshot was saved and no console-error audit was performed.
- [x] Frontend response/residual/localization labels are semantically accurate — evidence: `cd static-website && npm test` → 26 passed; `npm run build` passed; `git diff --check` passed. SAFE_MODE is labeled current-limited, the client-computed residual meter is identified as such, and localization is shown as a score rather than a percentage.
- [x] Clean source-copy backend setup — evidence: copied current source without `.git`, venvs, or caches; installed `backend/requirements.lock`, installed the package editable, then full backend pytest, Ruff, and strict mypy passed. This verifies a clean source copy, not a clean Git clone or committed release.
- [x] All-scenario soak — evidence: three rounds × seven scenarios at 60×; all 21 sessions delivered 600 frames without stream errors. `tracemalloc` current growth 4,456,522 bytes; peak growth 10,008,749 bytes. No acceptance threshold and no RSS/native allocation measurement, so memory acceptance remains open.

## P10 Release hardening
- [ ] Fresh-clone script passes end to end
- [x] Soak test: all scenarios × 3 at 60× with zero error frames — evidence: 21 sessions, all seven scenarios in each round, 600 frames per run; traced current growth 4,456,522 bytes and peak growth 10,008,749 bytes. No RSS/memory threshold was defined, so memory acceptance remains open.
- [ ] End-to-end failure/recovery drills pass, including backend loss and frontend recovery — browser walkthrough remains open.
- [x] Backend/API failure responses exercised: malformed main config unit check; missing, malformed, and uncalibrated `detection.yaml` degrades health and blocks sessions; missing results artifacts return 404; corrupt benchmark JSON returns 503; active WebSocket closes after terminating a real Uvicorn process (close code 1006). Repeat with `scripts/failure_drill.py` or `make failure-drill`. This does not establish graceful shutdown or frontend recovery.
- [ ] Playwright smoke passes (SHOULD)
- [ ] README complete; no TODO/FIXME/commented-out code (grep check)
- [ ] `make check` has zero warnings
- [x] Frontend dependency audit clean — evidence: `cd static-website; npm audit --audit-level=moderate` → 0 vulnerabilities on 2026-10-27; Python lockfile audit did not return a result because the vulnerability service request stalled.
- [x] Missing-calibration and missing-benchmark API drills have clear failure responses — evidence: `test_unavailable_calibration_degrades_health_and_blocks_sessions` and `test_missing_benchmark_artifacts_return_actionable_error` in `backend/tests/test_api.py`.
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

## User-requested real-data validation
- Deployment readiness summary and ordered blockers: `docs/DEPLOYMENT_READINESS.md`.
- [x] Public measured-cell voltage model experiment completed — evidence: `python scripts/validate_twin_calce.py` → 825 usable cycles parsed, 150 earlier cycles used for fitting, 248 later cycles held out; training RMSE 0.0563 V, held-out RMSE 0.1916 V; raw archive hash and limits in `docs/DATA_VALIDATION.md` and `data/results/calce_cs2_33_validation.json`
- [x] Separate-cell model generalization check completed — evidence: `scripts/validate_twin_calce_cross_cell.py`; fit on 150 early CS2_33 cycles, hold out all 775 CS2_34 cycles; RMSE 0.0919 V, MAE 0.0691 V, p95 0.1761 V. This does not satisfy or establish a deployment threshold.
- [x] Public validation data can be reproduced — evidence: `scripts/download_calce.py` verified pinned CS2_33 and CS2_34 SHA-256 values and extracted the archives under ignored `data/raw/calce/`.
- [ ] Independent multi-cell/pack validation, temperature sensing, BMS/CAN data, attack labels, and closed-loop response verification — blocked until target hardware/data and safety test setup exist; not evidenced by the CALCE cell dataset
- [x] Validation-only response recovery check — evidence: `scripts/validate_response_recovery.py --baseline-runs 100 --attack-runs 10 --workers 8`; baseline seeds 0–99 → 13 B3 alarm episodes / 100 h = 0.13/h, 13 SUSPECT, zero CONFIRMED/SAFE_MODE, zero hazards; attack seeds 0–9 measured separately. AT4 was detected in 1/10 sample runs.
- [x] Honest-baseline held-out measurement — updated seeds 1000–1199 report B3 0.160 false-alarm episodes/hour vs 0.135 for B2; target 0.20/hour met. Direct state audit: 30/200 entered SUSPECT, 27 cleared, zero CONFIRMED/SAFE_MODE, 3 remained SUSPECT at end. API serves updated results. B3 trails B2 for AT2/AT3/AT4/AT6 and runtime gate remains missed; this is a measurement, not deployment acceptance. Evidence: `data/results/p10_baseline_state_test.json`, `data/results/results.json`.

Scope note: the user explicitly selected `static-website/` as the primary frontend and asked to retain that frontend with the backend. P9 checkboxes above describe the originally planned React frontend; they are not evidence for the selected static site, and they must not be silently checked as complete. Reconcile P9 criteria with the approved static-site architecture before release sign-off.
  - [x] Final command-center alignment and header spacing — evidence: `cd static-website && npm run build` passed; `npm test` → 26 passed; `git diff --check` passed. The live dashboard now has a dedicated viewport-height row, its title aligns to the side panels, and detail sections flow below it. Browser visual confirmation remains pending.
