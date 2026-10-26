# PHASE_IMPLEMENTATION.md

Budgets are **wall-clock caps for Claude Code work**, not human time. Total build budget: about 30 h, leaving buffer inside a 48 h event. Phases marked **REVIEW** stop for the user's "go". Priority tags: **MUST / SHOULD / COULD**.

Order of dependency: P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P10 → P11. Backend phases P1–P7 must be finished and tested **before** the frontend starts, so the UI is built against a stable API. Current continuation point: P7 evaluation harness.

## Cut rules (apply automatically, log in PROGRESS.md)

Trigger: a phase exceeds 1.5x budget, or the clock passes the checkpoint below.

| Checkpoint (event hour) | Must be done | If not, cut in this order |
|---|---|---|
| H12 | P0–P3 | skip P1b (dataset validation), skip COULD items |
| H21 | P0–P6 | simplify localization to per-channel dominance only; drop `multi` logic |
| H27 | P0–P8 | drop S1/S2 permanently; drop ECharts annotations beyond limit lines |
| H35 | P9 core views (Console, Lab, Benchmarks) | merge Method into a single static page; drop Playwright |
| H38 | **Feature freeze** | no new features after this; only fixes, docs, packaging |
| H40 | P10 done, tag `v1.0.0` | skip Docker; keep `make serve` |
| H46 | Submit | nothing new |

Never cut: determinism, tests, honesty rules, offline replay mode, `make check`, `make eval` reproducibility, Limits content.

---

## P0 — Bootstrap (budget 0.75 h, MUST) — **COMPLETE**

**Goal:** a repo where `make check` runs green on trivial content, so every later phase has a working gate.

Tasks:
- `git init`; `.gitignore` (data/raw, venvs, node_modules, dist, `__pycache__`).
- Backend: `pyproject.toml`, package skeleton, `config.py` (pydantic models + YAML loader + config hash), logging setup, one passing test.
- Frontend: Vite + React + TS strict + Tailwind + ESLint + Vitest scaffold, fonts bundled via `@fontsource`, one passing test.
- `Makefile` with every target in CLAUDE.md section 7.
- `configs/default.yaml` with all starting parameters from SPEC.md sections 2–5.
- `docs/PROGRESS.md` initial entry.

Acceptance: `make setup && make check` passes from a clean clone; `make dev` starts both servers; `GET /api/health` returns JSON.

---

## P1 — Plant, twin, sensors, charger (budget 3 h, MUST) — **COMPLETE**

Tasks:
- `plant.py` (2-RC + Arrhenius-like R0(T) + thermal), `sensors.py` (noise + quantization, seeded), `charger.py` (profile controller + thermal derate), `twin.py` (1-RC), unit-to-unit variation.
- `pipeline.py` minimal loop: plant ↔ sensors ↔ charger with honest telemetry, producing a trajectory object.
- Unit tests: determinism (same seed → identical arrays), SOC monotone and charge-conserving, steady-state thermal analytic check (SPEC 2.3), OCV monotone, no NaN over 200 random configs, sign convention.
- Plausibility script `scripts/plot_nominal.py` writes PNG of honest and under-reported runs.
- Fit twin `tau1_n, R1_n` on validation data (least squares) and write to config.

**P1b — Dataset validation (COULD, timebox 90 min, skip at H12 cut):** if `data/raw/nasa/` contains a NASA PCoE battery file (user places it; do not scrape), write `scripts/validate_twin_nasa.py` that fits twin parameters on discharge cycles of one cell and reports voltage RMSE on held-out cycles, with a figure. If the file is missing, log "dataset not available" and mark the CLAIMS_EVIDENCE row **unsupported**. Do not report any dataset number that the script did not compute.

Gate: SPEC 2 plausibility targets 1–3 verified and printed; `make check` green; figure reviewed by user.

---

## P2 — Passive detection (budget 3.5 h, MUST) — **COMPLETE; held-out FA exceeds target slightly and is reported without retuning**

Tasks:
- `ekf.py` with Joseph update; `detectors/nis.py`, `detectors/cusum.py`, `detectors/range_check.py`.
- `eval/calibrate.py` + `make calibrate`: validation seeds 0–99, equal FA budget split, writes `configs/detection.yaml` with metadata.
- EKF unit tests on synthetic linear system (NIS mean near m, NEES bounds); numerical robustness tests (singular S raises `NumericalError`).
- Diagnostics: NIS QQ-plot script for the Method page (data only; plotting in frontend).

Gate: on validation seeds the combined passive FA ≤ `FA_target`; on **test** seeds FA measured once and recorded (no retuning). Report the real number even if above target, and add to Claims at risk.

---

## P3 — Attack engine (budget 3 h, MUST) — **COMPLETE; attack configuration frozen**

Tasks:
- `attacks/*` implementing AT1–AT6 per SPEC 6, with `configs/attacks.yaml`. Hooks: telemetry (`apply`), physical (`physical`), request (`request`).
- Scenario catalog `configs/scenarios.yaml`: ids `baseline`, `spike`, `drift`, `replay`, `model_synthesis`, `malicious_command`, `oracle_limit`, plus `story_ladder` (ordered steps for the guided demo).
- Tests: each attack respects its knowledge level (AT4 never reads `I_cmd` probe; AT6 does); AT1–AT5 outputs remain within static range limits where SPEC says so; hazard reachable undefended (SPEC 2 target 2).
- Stealth report script: B0/B1/B2 (no probe) detection rates on validation seeds per attack.

Gate: stealth requirements in SPEC 6 satisfied or attacks fixed; **`configs/attacks.yaml` frozen and committed with tag `attacks-frozen`**. After this tag, attack parameters change only with a PROGRESS.md "Deviation" entry and user approval.

---

## P4 — Localization (budget 2 h, SHOULD) — **COMPLETE**

Tasks: `localize.py` per SPEC 7, bank of V-only / T-only EKFs, dominance rule calibrated on validation seeds, confusion-matrix function in `eval/metrics.py`.

Gate: unit tests with synthetic single-channel faults; confusion matrix on validation for AT1, AT2 (single-channel T) printed.

Cut fallback: dominance-only rule (largest standardized residual), no `multi`.

---

## P5 — Active verification (budget 3.5 h, MUST) — **COMPLETE WITH AT4 LIMITATION**

Tasks:
- Keyed probe generator (`detectors/probe.py`) with fresh nonce per window, safe clipping, zero-mean property test.
- Gain estimator per SPEC 5 with high-pass; calibration of `g_min` on validation attack-free windows; V-only, I-only, combined tests.
- Probe scheduling (periodic and continuous modes).
- Amplitude sweep experiment (detection vs amplitude) and overhead measurement experiment.
- A2 oracle run to demonstrate the limit.

Tests: probe never violates limits; same key+nonce reproduces probe, different nonce differs; authentic telemetry gives ĝ near 1 on validation; AT3 replay gives ĝ near 0; measure and report AT4 separately because its attacker-visible current channel may expose the probe; replay of an old probe window fails.

Gate: measure AT3 and AT4 (V-only and combined) on validation, respect the FA budget, and generate sweep and overhead tables. If active verification does not beat B2 on AT4, **report that** and diagnose amplitude/window and attacker observability; tune on validation only. Record an unresolved frozen-attack limitation instead of changing P3 attack knowledge silently.

---

## P6 — Command guard, response, paired plants (budget 3 h, MUST) — **COMPLETE**

Tasks:
- `command_guard.py` (pessimistic forward simulation + bisection), `response.py` (state machine, SAFE_MODE actions, virtual sensor, operator reset).
- `pipeline.py` upgrade: run the **paired** plants (defended and undefended) from the same seed and attack; event stream (`events` with severity and text).
- Closed-loop tests: AT2/AT3/AT4/AT5 each produce lower peak hazard defended than undefended on validation seeds, or the failure is reported; no oscillation (state machine hysteresis test); operator reset logic test.

Gate: closed-loop summary table on validation seeds (peak T, peak V, hazard-event rate, defended vs undefended) printed. **Complete:** paired seeds 0–9 show lower peak T and V in every defended run for AT2–AT5; hazard rates were AT2 0%→0%, AT3 30%→0%, AT4 0%→0%, AT5 100%→0%. See `data/results/p6_closed_loop_summary.md` and `data/results/p6_closed_loop_report.json`.

---

## P7 — Evaluation harness (budget 3 h, MUST) — **CURRENT PHASE / TODO**

Tasks:
- `eval/runner.py` (multiprocessing, deterministic per-run seed, progress), `eval/metrics.py` (Wilson CI, delay stats, margins, hazard reduction, confusion), `eval/report.py` (results.json with pydantic schema, CSV, markdown tables, SVG figures: detector ladder bars, delay distributions, detection vs probe amplitude, confusion matrix, probe overhead).
- `make eval` on test seeds. `meta.json` with git hash, config hash, seeds, runtime.
- Repeatability test: run a reduced eval twice, compare JSON equality.
- S1 residual learner: **only if all earlier gates pass and time remains (COULD)**; with ablation.

Gate: `make eval` < 10 min; results validate against schema; repeatability test passes; results committed under `data/results/`.

---

## P8 — API and session engine (budget 3 h, MUST) — **REVIEW**

Tasks per SPEC 10: FastAPI app, session manager (limits, idle timeout, cleanup), WebSocket protocol with batching and speed control, `inject`, `pause/resume`, `reset`, `operator_reset`, `/api/benchmarks`, `/api/limits`, static serving of the built frontend, CORS for dev only, typed error mapping, JSON logging.
Recorder: `make demo-data` writes recorded runs for every scenario into `frontend/public/demo-runs/`.

Tests: REST validation errors, WS happy path, inject mid-run reproducibility (same seed + same injection time → identical frames), malformed WS messages return `error` frames without closing the server, session cleanup, 4-session concurrency, step-time budget.

Gate: `make check` green; a scripted WebSocket client runs all scenarios at 60× with zero errors; demo-runs recorded.

---

## P9 — Frontend (budget 8 h, MUST for 9a–9d, SHOULD for 9e–9f)

Read `docs/DESIGN.md` before starting. Sub-phases, each ends with `make check`, a screenshot set saved to `docs/screens/`, and a short REVIEW pause for the user to look at it.

- **9a Foundation (1.5 h):** design tokens in Tailwind config, typography, layout shell (nav, status bar), API client with runtime validation, WebSocket hook with reconnect/backoff, Zustand store, error boundary, connection states, **offline replay mode** (loads `demo-runs`), reusable `Chart` wrapper (ECharts, no animation on streams, windowed data), `StatusBadge`, `Metric`, `Panel` components with all states (loading, empty, error).
- **9b Live console (2.5 h):** per DESIGN.md: thermal trace hero (protected vs unprotected true temperature, reported, predicted, limits, attack window), evidence strip (NIS, CUSUM, probe gain), control strip (request, command, safe limit), state machine indicator, channel trust, event timeline, run controls (play/pause/speed/reset), attack injection dock.
- **9c Scenario lab and guided story (1.5 h):** scenario picker, the `story_ladder` guided demo with step captions that tie to the live run, seed input, share/reproduce text.
- **9d Benchmarks (1.5 h):** detector ladder table + bars, detection-vs-probe-amplitude curve, delay distributions, localization confusion matrix, probe overhead, run metadata, "reproduce with" command, honest failure rows displayed with equal prominence.
- **9e Method and limits (0.75 h, SHOULD):** architecture diagram (SVG), equations, threat-model table, limitations from `/api/limits`.
- **9f Polish and accessibility (0.75 h, SHOULD):** keyboard navigation, focus states, `prefers-reduced-motion`, presentation-scale toggle, responsive checks at 1280 and 768 widths, empty/error copy review.

Gate: Vitest component and store tests (WS message handling, offline fallback, error states), `tsc --noEmit`, ESLint, production build, bundle < 1.5 MB gzipped excluding fonts, manual walkthrough of DEMO_SCRIPT.md without console errors.

---

## P10 — Hardening and packaging (budget 4 h, MUST)

Tasks:
- Fresh-clone test script `scripts/fresh_clone_test.sh`: clone → `make setup` → `make check` → `make eval` (reduced) → `make serve` → HTTP and WS smoke.
- Soak test: scripted client runs every scenario at 60× three times; assert zero error frames, no memory growth beyond a threshold, no unhandled rejections in the frontend (Playwright if available; else a headless script using the WS client).
- Failure drills: kill backend mid-run (UI shows reconnect then offers replay); malformed config (clear error at startup); missing `detection.yaml` (health reports it, UI explains); missing `results.json` (Benchmarks view explains).
- Playwright E2E smoke: load console, start `story_ladder`, assert state transitions appear (SHOULD).
- Dockerfile (multi-stage) and `docker run` smoke (COULD).
- README: what it is, scope and limits, quick start, architecture, how results were produced, reproducibility, folder map. Remove dead code, unused deps, TODOs. License file.
- `make check` zero warnings. Tag `v1.0.0`.

Gate: all PHASE_CHECKLIST "Release" items ticked with evidence.

---

## P11 — Submission pack (budget 3 h, MUST) — **REVIEW**

Tasks:
- Fill `docs/CLAIMS_EVIDENCE.md` with real numbers and file paths; produce the final form text with only supported claims (drop or soften unsupported ones, list what changed).
- Record a 3-minute backup demo video of `story_ladder` (user records; Claude supplies the shot list from DEMO_SCRIPT.md).
- Q&A rehearsal sheet finalized from real results.
- Export figures for slides if the hackathon needs a deck (SVG/PNG from `data/results/figures`).

Gate: every claim in the submission text maps to evidence; backup video exists; `v1.0.0` tag checked out on the demo machine and `make serve` verified offline.

---

## Stretch items (only after P10 is green and the clock is before H38)

- **S1** ML residual learner with ablation (CLAIM only if test-seed results improve with CI).
- **S2** Adaptive probing cost panel (AI-08): measure monitoring compute and probe overhead versus always-on probing; show energy/time cost honestly.
- **S3** CALCE data validation.
- **S4** Pack-level (series cells) extension: not planned; mention as future work only.
