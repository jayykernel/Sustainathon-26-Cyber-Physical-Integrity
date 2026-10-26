# CLAIMS_EVIDENCE.md

Every claim in the submission text must map to evidence produced by the repository. Status values: `unverified` (default), `supported`, `softened` (text changed to match), `removed`. Claude updates this file; the user approves the final text.

Rule: if evidence does not exist at P11, the claim is softened or removed. Do not build evidence to fit a claim after seeing results.

| # | Claim in submission text | Evidence (file / command) | Status | Final wording or note |
|---|---|---|---|---|
| 1 | Digital twin of battery electrical and thermal behavior | `backend/src/physiguard/twin.py`, tests | unverified | |
| 2 | Twin calibrated and evaluated on public datasets (NASA/CALCE) | `data/raw/nasa/` absent; no public-dataset validation output | unsupported | No NASA PCoE file was supplied. Do not claim public-dataset validation; the twin was fitted and checked only against synthetic plant-generated validation data. |
| 3 | EKF with innovation-based chi-square testing | `ekf.py`, `detectors/nis.py`, NIS QQ diagnostic | unverified | Thresholds are empirical; chi-square is a diagnostic. Word it that way. |
| 4 | CUSUM catches gradual drift | `results.json` AT2 B1 vs B2 rows | unverified | |
| 5 | Residual signatures localize the suspected channel | confusion matrix in `results.json` | unverified | State accuracy and ambiguous cases. |
| 6 | Thresholds calibrated on attack-free validation data; false alarms measured on separate test data | `configs/detection.yaml`, `data/results/passive_fa_validation.json`, `data/results/passive_fa_test.json` | softened | Thresholds were calibrated on seeds 0–99. Held-out seeds 100–199 produced 0.2101 false alarms/hour, slightly above the 0.20/hour target; do not claim the test target was met. |
| 7 | Active random probe exposes replay and model-aware attacks that passive monitoring misses | AT3/AT4 rows for B2 vs B3; probe-amplitude curve | unverified | Only keep if B3 detection exceeds B2 with CI that does not overlap, or soften to the measured result. |
| 8 | We test against model-aware attackers | AT4 definition in `configs/attacks.yaml`; stealth report | unverified | |
| 9 | Virtual sensor estimates and conservative charging reduce simulated hazard | defended vs undefended rows in `results.json` | unverified | State per-scenario reduction, including scenarios with none. |
| 10 | Malicious but valid commands are blocked | AT5 rows; `command_guard.py` tests | unverified | |
| 11 | Reproducible red-team vs blue-team experiments | `make eval` repeatability test; `meta.json` | unverified | |
| 12 | Baseline comparison: range-based, EKF-only, EKF+CUSUM, full | `results.json` ladder | unverified | |
| 13 | Probe overhead is small | overhead table in `results.json` | unverified | Quote measured numbers only. |
| 14 | Addresses AI-01, AI-07, AI-10 | rows 4–5, 9 and the Console view; AI-10 evidence = paired-plant hazard view | unverified | AI-08 only if S2 shipped. |
| 15 | Complements UN R155 / ISO/SAE 21434 practices | none (positioning statement) | unverified | Keep as "complements"; never "compliant". |
| 16 | Extends to chargers, fleets, stationary storage | none (future work) | unverified | Phrase as future work unless demonstrated. |
| 17 | Learned/ML component (if mentioned anywhere) | S1 ablation in `results.json` | unverified | Remove ML wording if S1 not shipped. |

## Claims at risk (Claude adds items here during the build)
- Combined passive false alarms measured 0.2101/hour on held-out attack-free seeds, slightly above the 0.20/hour target. This is reported without retuning on test data.

## Tech stack text must match
- Remove `filterpy` (EKF is in-repo).
- Include `scikit-learn` only if S1 shipped.
- Include `PyBaMM` only if actually used (default plan: custom equivalent-circuit model).
- Frontend: React, TypeScript, Vite, Tailwind, ECharts, Zustand. Backend: Python, NumPy, SciPy, FastAPI, pydantic.

## Final submission text
(Claude writes the final version here in P11 after all rows are resolved. The user pastes it into the form.)
