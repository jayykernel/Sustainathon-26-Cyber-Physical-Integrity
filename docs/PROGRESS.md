# PROGRESS.md

Living log. Update after each task and phase so the current implementation state and evidence stay visible.

## Current status
- Current phase: P2 (P1 complete)
- Event clock at last update: 2026-10-26 (start time = 2026-10-26 00:00 local)
- Last green `make check`: 2026-10-26
- Tags: none
- Continuation session: P0 was reverified from the committed tree. P1 implementation, acceptance tests, measured scenarios, fitted twin parameters, and user review of the plausibility figure are complete.

## Phase log
| Phase | Status | Budget | Used | Gate evidence | Notes |
|---|---|---|---|---|---|
| P0 Bootstrap | complete | 0.75 h | | `make setup && make check`; `make dev`; fresh source-copy setup/check; committed-tree `make check` | 14 backend tests and 1 frontend test passed at P0 completion; P0 reverified after push. |
| P1 Plant/twin | complete | 3 h | | `make check`; `make fit-twin`; `make plot-nominal`; user reviewed figure | 22 backend tests and 1 frontend test pass; all MUST criteria met. NASA P1b unavailable and unsupported. |
| P2 Passive detection | todo | 3.5 h | | | |
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
- The workspace initially had only the README tracked. P0 was later split into ten commits and pushed to `origin/main`; P1 changes remain uncommitted pending phase review.

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

## Deviations, risks, and cuts
- The P0 clean-room verification used a fresh source copy with generated environments/dependencies/build outputs excluded, not a Git clone, because project implementation files are untracked user work.
- `npm ci` advisory counts are unchanged; dependency remediation remains parked for a compatibility-focused update.

## Exact continuation point
- Next: begin P2 passive detection.
- P0 was pushed in ten commits as requested. P1 is being committed in eight focused commits; no tag is created.

## Measured numbers log
`P0 | make check | backend tests | 14 passed | — | 87950a9351118e47`
`P0 | make check | frontend tests | 1 passed | — | —`
`P0 | npm ci | dependency advisories | 15 (6 moderate, 7 high, 2 critical) | — | —`
`P1 | make plot-nominal | honest peak T / peak V / final SOC | 45.98 °C / 4.1937 V / 0.9444 | 11 | —`
`P1 | make plot-nominal | under-reported thermal hazard time | 23.10 min | 11 | —`
`P1 | make plot-nominal | 150 A CV hijack to voltage hazard | 141 s after attack onset | 11 | —`
`P1 | make fit-twin | R1_n / tau1_n / polarization RMSE | 0.001083371522 Ω / 55.23743011 s / 0.00228423 V | 10000 | —`

## Ideas parked
- Remediate npm audit advisories in a dedicated dependency update with compatibility checks.

## Blockers / needs from user
- No active blockers. NASA P1b was skipped because the dataset is unavailable; the associated public-validation claim is unsupported.
