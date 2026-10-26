# PROGRESS.md

Living log. Update after each task and phase so the current implementation state and evidence stay visible.

## Current status
- Current phase: P3 (P2 complete)
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
| P3 Attack engine | todo | 3 h | | | |
| P4 Localization | todo | 2 h | | | |
| P5 Active verification | todo | 3.5 h | | | |
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

## Exact continuation point
- Next: begin P3 attack engine.
- P0 was pushed in ten commits and P1 in eight focused commits. P2 work is uncommitted; no new tag was created.

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

## Ideas parked
- Remediate npm audit advisories in a dedicated dependency update with compatibility checks.

## Blockers / needs from user
- No active blockers. P2 test false alarms are slightly above target and are documented without retuning; NASA P1b remains unavailable and unsupported.
