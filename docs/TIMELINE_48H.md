# TIMELINE_48H.md — your plan (for you, not for Claude)

H0 = the moment the hackathon starts. Claude Code does the building; you supply decisions, reviews, sleep, and the final presentation. Expect about **10 hours of your own attention**, spread out. Phase budgets are caps; if Claude finishes early, you gain slack.

## Before H0 (do this the day before; about 1 hour)
- [ ] Install: Python 3.11+, `uv` (optional), Node 20+, git, Make, Claude Code. Run each `--version`.
- [ ] Check your Claude Code usage limits. Long phases can hit them. If you do, the work simply resumes next window; keep PROGRESS.md current so resuming is cheap.
- [ ] Optional but valuable: download one NASA PCoE battery cell file (for example the B0005 `.mat` from the NASA Prognostics Data Repository) and place it in `data/raw/nasa/`. If you skip this, the form text must not claim dataset calibration.
- [ ] Create an empty repo folder; copy this documentation set into it (`CLAUDE.md` at root, the rest in `docs/`).
- [ ] Read `docs/DEMO_SCRIPT.md` once so you know where this is going.

## Schedule

| Event hour | Claude Code works on | You do | Check |
|---|---|---|---|
| H0–1 | (starting) | Place docs, run Claude Code in the repo, paste `docs/INITIAL_PROMPT.md`. Fill in event start time in PROGRESS.md. | Claude prints the P0 plan |
| H1–4.75 | P0, P1 | Away. At the P1 REVIEW (about 15 min): look at the plots. Does the honest run stay cool and the attacked run overheat? Reply "go". | Gate: SPEC 2 targets |
| H4.75–11.25 | P2, P3 | Away. At the P3 REVIEW (about 30 min): read the stealth report. Is the model-synthesis attack actually invisible to passive tests? Approve the attack freeze. | Gate: `attacks-frozen` tag |
| H11.25–16.75 | P4, P5 | Away. At end of P5 (about 30 min): read the active-verification numbers. If they are weak, say so and let Claude diagnose; do not ask for nicer numbers. | Checkpoint H12: P0–P3 done |
| H16.75–17.5 | | Reply "go P6, continue to P7 if the P6 gate is green, stop after P7." Go to sleep. | |
| H17.5–24 | P6, P7 (unattended) | **Sleep (6.5 h)** | |
| H24–25 | | Morning review (30 min): read the eval tables and the closed-loop hazard table. Decide what claims survive. Reply "go P8". | Checkpoint H21: P0–P6 done |
| H25–28 | P8 | Light attention. P8 REVIEW (15 min): confirm demo-runs exist. Reply "go P9". | Checkpoint H27: P0–P8 done |
| H28–31 | P9a, 9b, 9c | Look at screenshots after each sub-phase (10 min each). Say what looks wrong in plain words; Claude fixes. | |
| H31–33 | P9d, 9e | **Nap (2 h)** | |
| H33–35 | P9f | Click through the console yourself with the DEMO_SCRIPT. Note rough edges. | Checkpoint H35: core views done |
| H35–39 | P10 | Light attention; run the fresh-clone script yourself on a second machine if you can. | **H38 feature freeze** |
| H39–40 | | Tag `v1.0.0`. Check offline demo on the presentation machine. | Checkpoint H40 |
| H40–44 | P11 | Review CLAIMS_EVIDENCE with Claude. Approve final text. Record the backup video. Rehearse twice. | |
| H44–46 | | Paste final text into the form. Verify submission. | |
| H46–48 | | Buffer. Do not start anything new. | |

## Rules for you
1. **Never ask for better numbers.** Ask for diagnosis. If you pressure the results, you invalidate the work and judges can tell.
2. **Say "go" explicitly** at REVIEW phases. If you are unavailable, Claude waits; that is better than guessing.
3. **If you fall behind**, let the cut rules in `PHASE_IMPLEMENTATION.md` apply automatically. The order of cuts is already decided so you do not have to decide while tired.
4. **Protect the last 8 hours.** The submission text and the rehearsal matter as much as the code.
5. **Do not demo anything you have not run on the demo machine.**

## What you must understand well enough to answer judges (study in the gaps)
- What the EKF innovation is and why model mismatch makes thresholds empirical.
- What CUSUM adds over a window test (accumulating small persistent bias).
- Why the model-synthesis attacker passes passive checks.
- What the probe gain means (about 1 authentic, about 0 forged) and why a keyed random sequence matters.
- Why the oracle attacker defeats the probe, and what the Limits page says.
Questions 1–12 in `docs/DEMO_SCRIPT.md` are the likely ones.
