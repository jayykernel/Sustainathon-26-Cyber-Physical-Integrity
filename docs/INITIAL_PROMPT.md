# INITIAL_PROMPT.md

Paste everything inside the box into Claude Code, run from the project root (where `CLAUDE.md` lives).

```
You are building PhysiGuard for a 48-hour hackathon. Your operating rules are in CLAUDE.md in this folder. Read it fully now, then read docs/PROGRESS.md and docs/PHASE_IMPLEMENTATION.md. Read docs/SPEC.md before any backend code and docs/DESIGN.md before any frontend code.

Goal: a stable, demo-safe, honest simulation prototype: a battery digital twin with EKF and CUSUM detection, channel localization, active randomized current-probe verification, a command guard, a conservative response, a reproducible evaluation harness, a FastAPI + WebSocket backend, and a mature interactive React frontend. It must run offline with one command and must not break during a live demo.

Start with phase P0 only.
1. Write your P0 plan (5-10 lines) into docs/PROGRESS.md.
2. Implement P0 per docs/PHASE_IMPLEMENTATION.md.
3. Run the gate (make setup && make check) and fix until green.
4. Tick the P0 items in docs/PHASE_CHECKLIST.md with evidence, update docs/PROGRESS.md, commit, and tag phase-0-done.
5. Print the phase report in the format from CLAUDE.md section 9.
6. Continue directly to P1. Stop at each phase marked REVIEW and wait for me to say "go".

Autonomy and rules in effect:
- Decide small things yourself and log them under Decisions in PROGRESS.md. Ask me only when blocked by something only I can provide.
- Never fabricate or hardcode results. Every number must come from code you ran. Report failures as measured.
- Calibrate on validation seeds 0-99 only; report on test seeds 1000-1199 only.
- Freeze attack definitions at the P3 gate before tuning the defender.
- Apply the cut rules in PHASE_IMPLEMENTATION.md automatically if a phase exceeds 1.5x its budget. Log every cut.
- Keep make check green at every commit.
- If I say "go P6, continue to P7 if the P6 gate is green, stop after P7", treat that as permission to pass the P6 REVIEW without waiting, but stop immediately on any red gate.

Tell me the exact event start time you assumed (or ask me for it once, now), then begin P0.
```

## Resuming in a new session
```
Resume PhysiGuard. Read CLAUDE.md, then docs/PROGRESS.md, then find the current phase in docs/PHASE_IMPLEMENTATION.md. Report the current phase, the last green gate, and any open blockers in five lines, then continue the operating protocol.
```

## Asking for a fix after a review
```
REVIEW FEEDBACK for phase <N>: <what you saw, in plain words>.
Diagnose the cause with a failing test first, fix the root cause, re-run the phase gate, update PROGRESS.md and the checklist, and re-print the phase report. Do not change thresholds, attack definitions, or metrics to make results look better.
```

## If Claude proposes something out of scope
```
That is out of scope for the current phase. Log it under "Ideas parked" in docs/PROGRESS.md and continue with the current phase.
```
