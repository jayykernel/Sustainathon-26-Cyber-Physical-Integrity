# AGENTS.md — PhysiGuard

Read this file fully at the start of every session. It overrides your defaults.

## 1. What this project is

PhysiGuard is a **simulation-based cyber-physical security prototype** for EV charging. It detects telemetry and commands that are digitally valid but physically inconsistent with a battery digital twin, localizes the suspect channel, verifies telemetry authenticity with randomized current probes (active challenge-response), and responds with a conservative charging policy. A FastAPI backend streams a live simulation to the user-selected `static-website/` frontend. A reproducible evaluation harness produces the benchmark numbers shown in the UI.

Hackathon: **48 hours total**. Problem statements targeted: AI-01 (primary), AI-07 (localization), AI-10 (cyber-to-physical impact). AI-08 (adaptive monitoring cost) is a stretch.

The goal is a **stable, demo-safe, honest** submission, not the maximum number of features.

## 2. Document map (read on demand, not all at once)

| File | Read when |
|---|---|
| `docs/SPEC.md` | Before implementing any backend module. Source of truth for models, equations, interfaces, API, metrics. |
| `docs/PHASE_IMPLEMENTATION.md` | At session start, to find the current phase and its acceptance criteria. |
| `docs/PHASE_CHECKLIST.md` | After every task. Tick items only with evidence. |
| `docs/DESIGN.md` | Before any frontend work. |
| `docs/PROGRESS.md` | At session start (to resume) and after every task (to log). |
| `docs/CLAIMS_EVIDENCE.md` | Before changing any user-facing claim, and in phase P11. |
| `docs/DEMO_SCRIPT.md` | In phases P10 and P11. |

If documents conflict: SPEC.md wins for behavior, DESIGN.md wins for UI, this file wins for process.

## 3. Operating protocol (follow exactly)

1. **Resume:** read `docs/PROGRESS.md`, find the current phase in `docs/PHASE_IMPLEMENTATION.md`.
2. **Plan:** write a 5–10 line plan for the phase into `docs/PROGRESS.md` before coding.
3. **Implement in small vertical steps.** After each step run the relevant tests. Never stack unverified changes.
4. **Gate:** at phase end run `make check` plus the phase-specific commands. All must pass.
5. **Record:** tick `docs/PHASE_CHECKLIST.md` with a one-line evidence note (command + result), update `docs/PROGRESS.md`, commit, and tag `phase-<N>-done`.
6. **Report:** print the phase report (format in section 9), then **stop and wait** for the user's "go" if the phase is marked REVIEW in PHASE_IMPLEMENTATION.md; otherwise continue to the next phase.
7. **Do not ask questions you can decide yourself.** Choose the simplest option consistent with SPEC.md, log it under "Decisions" in PROGRESS.md, and continue. Ask only if blocked by something only the user can supply (a file, credential, or a choice that changes a claim).

## 4. Non-negotiable rules

**Honesty (most important)**
- Never hardcode, fabricate, estimate, or "illustrate" any result, metric, or benchmark. Every number shown anywhere (UI, README, docs) must come from `make eval` output or a live run.
- Never tune thresholds or models on test seeds. Validation seeds 0–99 for calibration; test seeds 1000–1199 for reporting. See SPEC.md section 9.
- Freeze attack definitions (`configs/attacks.yaml`) before tuning the defender (phase P3 gate). Do not weaken attackers to flatter the defense, and do not strengthen the defense using knowledge of test results.
- If the defense fails against a scenario, report it as measured. Failures go in the Limits view and in results. They are not bugs to hide.
- If something in the submission text cannot be backed by evidence, add it to "Claims at risk" in `docs/CLAIMS_EVIDENCE.md`; do not silently keep or drop it.
- If a dataset or download is unavailable (no network, missing file), say so in PROGRESS.md and use the documented fallback. Never invent dataset results.

**Engineering**
- Everything is deterministic given (config hash, seed). No unseeded randomness. No wall-clock dependence inside the simulation.
- No `TODO`, `FIXME`, commented-out code, `print` debugging, or placeholder data in code that ships. Use the logger.
- No bare `except:`; no silently swallowed exceptions. Errors are typed, logged, and surfaced (API error frames, UI error states).
- All external inputs (HTTP, WebSocket, config files) are validated with pydantic (backend) or zod-style runtime guards (frontend).
- Single source of truth for parameters: `configs/*.yaml`. No magic numbers in code.
- Type hints everywhere in Python (`mypy --strict` on `src/`). TypeScript `strict: true`, no `any` without a justified comment.
- Keep dependencies minimal. Before adding one, check if the standard library or an existing dependency covers it. Pin versions (`uv.lock` or `requirements.lock`, `package-lock.json`).
- Do not use `filterpy`. The EKF is implemented in-repo (`ekf.py`) so it can be unit-tested and explained.
- Do not use `localStorage` for anything that affects correctness. UI preferences only.
- Fonts and assets are bundled locally. The demo must run **offline**.

**Scope control**
- Work only on the current phase. No "while I'm here" features.
- Priority tags: MUST / SHOULD / COULD. Never start a COULD item until all MUST and SHOULD items of all earlier phases pass. See cut rules in PHASE_IMPLEMENTATION.md.
- A phase exceeding 1.5x its time budget triggers the cut rules. Log it and cut; do not push through.

## 5. Tech stack (fixed — do not substitute)

**Backend (`backend/`)**: Python 3.11+, NumPy, SciPy, pydantic v2, PyYAML, FastAPI, uvicorn, pytest, ruff, mypy. Optional stretch: scikit-learn (residual learner only). Package manager: `uv` if available, else `pip` + venv with a lock file.

**Frontend (`frontend/`)**: Vite, React 18, TypeScript (strict), Tailwind CSS, Radix UI primitives, Apache ECharts (direct integration via `echarts` with a thin wrapper component), Zustand, lucide-react, `@fontsource/ibm-plex-sans` (+ `ibm-plex-mono` for code only). Tests: Vitest + React Testing Library; Playwright for one E2E smoke (SHOULD).

**Approved project-specific frontend decision:** the user explicitly selected `static-website/` as the primary frontend paired with the backend. It uses Vite, strict TypeScript, Three.js, and native DOM/CSS. The separate React `frontend/` folder is legacy and must not be used by the normal launcher or deployment unless the user changes this decision. This explicit choice supersedes the generic frontend stack and layout above; it does not authorize changing the backend or simulation architecture.

**Run modes**: `make dev` (hot reload, two processes), `make serve` (production: FastAPI serves the built frontend on one port, default 8000).

## 6. Repository layout

```
physiguard/
├── AGENTS.md
├── README.md                    # written in P10
├── Makefile
├── configs/
│   ├── default.yaml             # plant, twin, sensors, charger, limits
│   ├── attacks.yaml             # frozen at P3 gate
│   ├── detection.yaml           # thresholds written by calibration (generated)
│   └── scenarios.yaml           # named scenarios for UI + eval
├── data/
│   ├── raw/                     # user-supplied NASA/CALCE files (gitignored)
│   └── results/                 # eval outputs (committed: results.json, tables, figures)
├── docs/                        # this documentation set
├── backend/
│   ├── pyproject.toml
│   ├── src/physiguard/
│   │   ├── config.py  plant.py  twin.py  sensors.py  charger.py  ekf.py
│   │   ├── detectors/ (range_check.py nis.py cusum.py probe.py)
│   │   ├── attacks/   (base.py spike.py drift.py replay.py model_synthesis.py command.py oracle.py)
│   │   ├── localize.py  command_guard.py  response.py  pipeline.py
│   │   ├── eval/      (runner.py metrics.py calibrate.py report.py)
│   │   ├── api/       (app.py routes.py ws.py schemas.py sessions.py)
│   │   └── cli.py
│   └── tests/
└── frontend/
    ├── package.json  vite.config.ts  tailwind.config.ts
    ├── public/demo-runs/        # recorded runs for offline replay mode
    └── src/ (app/ components/ features/{console,lab,benchmarks,method}/ lib/ store/ styles/)
```

## 7. Commands (create all in P0; keep them working)

```
make setup       # install backend + frontend deps
make dev         # backend :8000 + frontend :5173 (proxy /api)
make test        # pytest + vitest
make lint        # ruff + eslint
make typecheck   # mypy --strict + tsc --noEmit
make fit-twin    # fit nominal 1-RC parameters on the fixed validation seed
make plot-nominal # save honest and attack plausibility trajectories
make calibrate   # validation seeds 0–99 -> configs/detection.yaml + diagnostics
make eval-passive # frozen thresholds -> one-time test seeds 100–199 false-alarm report
make eval        # test seeds -> data/results/*  (must finish < 10 min)
make build       # frontend production build
make serve       # single-port production server
make demo-data   # record demo runs into frontend/public/demo-runs
make check       # lint + typecheck + test + build  (THE GATE; must pass before every commit to main)
```

## 8. Definition of done (any task)

A task is done only when: code written, unit tests added and passing, `make check` green, checklist item ticked with evidence, PROGRESS.md updated. "It should work" is not evidence.

## 9. Phase report format (print at the end of every phase)

```
PHASE <N> REPORT
Status: PASS | PASS-WITH-CUTS | BLOCKED
Time vs budget: <used>/<budget>
Gate evidence: <commands run and results, 1 line each>
Measured numbers (if any): <only real outputs>
Cuts/deviations: <what, why>
Claims affected: <anything in CLAIMS_EVIDENCE.md that changed>
Next: <next phase> (waiting for "go" | continuing)
```

## 10. Style

- Python: ruff defaults + isort, docstrings on public functions stating units (SI: seconds, amperes, volts, kelvin offsets in °C, ohms, farads, joules).
- Sign convention: **current > 0 is charging** everywhere.
- Commit messages: conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). Small commits.
- UI copy: sentence case, active voice, plain words. Errors say what happened and what to do. See DESIGN.md.

## 11. When something breaks

1. Reproduce with a failing test first.
2. Fix the root cause. Do not loosen a test or threshold to make it pass.
3. If a fix would change a published claim or a gate, log it in PROGRESS.md under "Deviations" and flag it in the phase report.
