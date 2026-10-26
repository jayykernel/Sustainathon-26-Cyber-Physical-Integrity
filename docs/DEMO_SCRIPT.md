# DEMO_SCRIPT.md

Three-minute demo, then Q&A. Rehearse at least twice before submission. Numbers in brackets come from the live run or `results.json`; never say a number you did not read off the screen.

## Setup checklist (5 minutes before)
- Demo machine on `v1.0.0`, `make serve`, browser at `http://localhost:8000`, presentation-scale on, zoom 100%.
- Network off to prove it works offline (optional but strong). Backup video open in another tab.
- Console view, scenario `story_ladder` loaded, speed 20×, seed fixed.

## Script (3:00)

**0:00–0:25 Problem.** "Chargers and vehicles trust sensor values that pass digital checks. An attacker with a compromised data path can send values that are well-formed and in range, yet physically impossible. Normal cybersecurity checks that data is valid. We check whether it is true."

**0:25–0:50 Setup on screen.** Point at the two traces. "Same battery, same attack, same random seed. Blue is protected by PhysiGuard. Red is not. The dashed line is what the sensors report. The thin line is what our physics model expects."

**0:50–1:15 Step 1–2: spike and drift.** Press Play on the ladder. "A spike is easy: every detector catches it. Now a slow drift, half a degree per minute, far below sensor noise. A threshold check never sees it. Accumulated evidence does, after [delay] seconds." Point at CUSUM strip.

**1:15–1:55 Step 3: the model-aware attack.** "Now the interesting one. This attacker knows our physics model. It generates telemetry that fits the model perfectly while the real battery loses cooling." Point at red trace climbing and the quiet evidence strips. "Every passive test is silent. This is where physics-only monitoring fails. We show it failing."

**1:55–2:30 Step 4: the probe.** "Our fix: the charger adds a tiny random current wiggle the attacker cannot predict. The real battery's voltage responds. Forged data does not. Probe gain on the real battery is near one; on the forged data it is near zero." Point at probe gain strip. "The guard confirms the attack [delay] seconds after onset, switches to a virtual sensor, and limits the charge current. Blue peaks at [peak T]; red reaches [peak T] in simulation."

**2:30–2:50 Step 5: limits.** "If the attacker also sees the probe in real time, this check fails. We show that case in the same run and in the Benchmarks. We are a simulation prototype, not a certified safety system."

**2:50–3:00 Close.** "Physical consistency becomes a security signal: detect, localize, and limit the damage. Everything you saw is reproducible with one command, with measured results including failures."

## If something breaks
| Failure | Action |
|---|---|
| Backend not reachable | UI offers "Replay a recorded run". Say: "This is a recorded run from the same simulator." Continue script. |
| Browser glitch | Reload; state is deterministic by seed. |
| Everything fails | Play backup video; run Benchmarks page from static results if available. |

## Likely questions (answer from evidence; fill brackets from results)
1. **Is this real data?** Simulation. The twin is [validated against NASA data with RMSE ___ / parameterized from literature, not dataset-validated: say whichever is true]. Real deployment needs hardware validation.
2. **Why not just train an anomaly-detection model?** Learned detectors need attack data and can be evaded by data that stays inside the learned distribution. A physics model gives an interpretable reference, and the probe adds something the attacker cannot learn.
3. **What stops the attacker from guessing the probe?** It comes from a keyed, fresh-per-window random sequence. An attacker without the key cannot predict it. An attacker who sees `I_cmd` in real time can forge it; that is scenario AT6 and we report it as a failure case.
4. **Does the probe harm the battery?** Zero-mean, 4% of request current, clipped to limits. Measured overhead: [extra heating ___ °C, charge-time change ___, efficiency change ___] from `results.json`.
5. **How did you set false alarms?** Thresholds are empirical, calibrated on validation seeds 0–99, and false alarms are measured on separate test seeds: [___ per hour, CI ___]. Chi-square is used as a diagnostic, not the threshold source, because model mismatch breaks the textbook assumption.
6. **Did you tune on the test set?** No. Seeds are separated and the harness asserts it.
7. **How good is localization?** [Confusion matrix]. Forged-everything attacks are reported as `multi`; single-channel attacks [accuracy ___]. We say where it is ambiguous.
8. **Why does the model-aware attack fool passive monitoring?** It generates telemetry from the same physics, so residuals stay inside noise. Without a secret challenge there is nothing to distinguish forged from real.
9. **Does it scale to a pack or a fleet?** Not claimed. Single-cell-equivalent model. The principle extends; pack-level coupling is future work.
10. **What about aging or temperature drift in the model?** Not modeled. Unit-to-unit variation and ambient drift are; aging is future work and listed in Limits.
11. **Where is the AI?** [If S1 shipped: the learned residual model, with ablation ___. If not: say plainly that the core is physics-based estimation and statistical detection; the learned component was out of scope this round.]
12. **Relation to UN R155 / ISO 21434?** It complements cyber-risk management by adding a physical-consistency control. We make no compliance claim.

## Recording shot list (backup video)
1. Title and one-sentence problem (5 s). 2. Console at 20× running the ladder with captions (150 s). 3. Benchmarks page: ladder table, probe-amplitude curve, failure rows (20 s). 4. Limits page (5 s). Screen capture at 1920×1080, no notifications, mouse movement slow.
