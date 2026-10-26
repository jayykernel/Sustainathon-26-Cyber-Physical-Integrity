# PROGRESS.md

Living log. Update after each task and phase so the current implementation state and evidence stay visible.

## Current status
- Current phase: P0 complete; P1 is next
- Event clock at last update: 2026-10-26 (start time = 2026-10-26 00:00 local)
- Last green `make check`: 2026-10-26
- Tags: none
- Continuation session: P0 bootstrap blockers and root causes fixed; the full check passes in the working tree and a clean source copy.

## Phase log
| Phase | Status | Budget | Used | Gate evidence | Notes |
|---|---|---|---|---|---|
| P0 Bootstrap | complete | 0.75 h | | `make setup && make check`; `make dev`; fresh source-copy setup/check | 14 backend tests and 1 frontend test pass; Ruff, strict mypy, ESLint, TypeScript, and frontend production build pass. |
| P1 Plant/twin | todo | 3 h | | | P0 repair includes basic plant/twin correctness and regression tests; full P1 acceptance criteria remain. |
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
- No implementation files were committed or tagged. Git state began as README-only tracked content plus pre-existing untracked project files.

## Confirmed root causes and fixes
- Frontend could not build because `src/App` was absent, Vitest globals lacked types, and the PostCSS config used CommonJS in an ESM package. Added a minimal app, explicit Vitest/jest-dom imports, and ESM PostCSS config; frontend checks now pass.
- Make targets hid ESLint, mypy, and TypeScript failures and referenced a nonexistent backend path. Reworked targets to run actual checks, fail on errors, support Windows paths, and added missing typecheck and development supervision scripts.
- Backend strict checks exposed partially implemented plant/twin code with undefined names, incorrect config access and thermal equations, weak covariance handling, and missing validation. Repaired these issues and added deterministic simulation, validation, and EKF regression coverage.
- Test setup failed to provide the HTTP client dependency required by the installed Starlette test client. Declared the compatible test dependency and generated a pinned requirements lock.
- Config loading, timestamp handling, package metadata, and startup logging had gaps; fixed config validation/defaults, timezone-aware JSON timestamps, package typing metadata, and startup config-hash logging.

## Deviations, risks, and cuts
- `npm ci` reports 15 dependency advisories (6 moderate, 7 high, 2 critical). P0 checks pass, but dependency remediation remains a follow-up item; no blanket upgrade was applied during this phase.
- The P0 clean-room verification used a fresh source copy with generated environments/dependencies/build outputs excluded, not a Git clone, because project implementation files are untracked user work.
- P0 repairs to plant/twin resolve current lint/type/test defects; they do not complete P1's physical validation and acceptance criteria.

## Exact continuation point
- Next: start P1 by validating plant/twin behavior against the remaining checklist: SOC and charge conservation, analytic thermal steady state, honest and attacked hazard trajectories, randomized finite outputs, and twin fitting/validation evidence.
- Do not commit or tag unless the user explicitly asks; the implementation files remain untracked user work.

## Measured numbers log
`P0 | make check | backend tests | 14 passed | — | 87950a9351118e47`
`P0 | make check | frontend tests | 1 passed | — | —`
`P0 | npm ci | dependency advisories | 15 (6 moderate, 7 high, 2 critical) | — | —`

## Ideas parked
- Remediate npm audit advisories in a dedicated dependency update with compatibility checks.

## Blockers / needs from user
- None for P0. P1 implementation and validation are the next work phase.
