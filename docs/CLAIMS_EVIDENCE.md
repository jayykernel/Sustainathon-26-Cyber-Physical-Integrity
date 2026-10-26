# CLAIMS_EVIDENCE.md

Every claim in the submission text must map to evidence produced by the repository. Status values: `unverified` (default), `supported`, `softened` (text changed to match), `removed`. Claude updates this file; the user approves the final text.

Rule: if evidence does not exist at P11, the claim is softened or removed. Do not build evidence to fit a claim after seeing results.

| # | Claim in submission text | Evidence (file / command) | Status | Final wording or note |
|---|---|---|---|---|
| 1 | Digital twin of battery electrical and thermal behavior | `backend/src/physiguard/twin.py`, tests | unverified | |
| 2 | Twin calibrated and evaluated on public datasets (NASA/CALCE) | `data/raw/nasa/` absent; no public-dataset validation output | unsupported | No NASA PCoE file was supplied. Do not claim public-dataset validation; the twin was fitted and checked only against synthetic plant-generated validation data. |
| 3 | EKF with innovation-based chi-square testing | `ekf.py`, `detectors/nis.py`, NIS QQ diagnostic | unverified | Thresholds are empirical; chi-square is a diagnostic. Word it that way. |
| 4 | CUSUM catches gradual drift | `data/results/stealth_report.json` AT2 B1 vs B2 | supported | On validation seeds 0–99, B1 caught 32% and B2 caught 90%; B2 median delay among detections was 1165.5 s. |
| 5 | Residual signatures localize the suspected channel | `data/results/localization_report.json` AT1/AT2 confusion matrices | supported | On validation seeds 0–99, temp-dominant localization was correct for 100/100 AT1 runs and 85/100 AT2 runs; 5 AT2 runs were unknown and 10 had no localization output. |
| 6 | Thresholds calibrated on attack-free validation data; false alarms measured on separate test data | `configs/detection.yaml`, `data/results/passive_fa_validation.json`, `data/results/passive_fa_test.json` | softened | Thresholds were calibrated on seeds 0–99. Held-out seeds 100–199 produced 0.2101 false alarms/hour, slightly above the 0.20/hour target; do not claim the test target was met. |
| 7 | Active random probe exposes replay and model-aware attacks that passive monitoring misses | `data/results/probe_report.json`, `data/results/probe_amplitude_sweep.svg` | softened | At 4% amplitude, active gain detects AT3 on 100% of validation runs, but detects AT4 on 3% combined versus 27% B2 without probing (29% B2-with-probe). The probe does not establish improved AT4 detection. |
| 8 | We test against model-aware attackers | AT4 definition in `configs/attacks.yaml`; `data/results/stealth_report.json` | supported | AT4 is a no-command/no-probe model-synthesis attacker; B2 caught 27% on validation seeds 0–99. |
| 9 | Virtual sensor estimates and conservative charging reduce simulated hazard | `data/results/p6_closed_loop_report.json`, `data/results/p6_closed_loop_summary.md`; virtual sensor tests | supported | On paired validation seeds 0–9, mean peak temperature and voltage were lower for AT2–AT5. Hazard rates changed AT2 0%→0%, AT3 30%→0%, AT4 0%→0%, and AT5 100%→0%. This is simulated evidence on 10 seeds. |
| 10 | Malicious but valid commands are blocked | AT5 rows in `data/results/p6_closed_loop_report.json`; `backend/tests/test_response.py` command guard coverage | supported | Across validation seeds 0–9, the undefended AT5 runs reached a hazard in 10/10 cases; defended runs reached a hazard in 0/10. |
| 11 | Reproducible red-team vs blue-team experiments | `make eval` repeatability test; `meta.json` | unverified | |
| 12 | Baseline comparison: range-based, EKF-only, EKF+CUSUM, full | `results.json` ladder | unverified | |
| 13 | Probe overhead is small | overhead table in `data/results/probe_report.json` | supported | Across 20 paired validation runs, mean peak temperature changed by +0.0118 °C, final temperature by +0.0020 °C, time to 90% SOC by +1.25 s, and estimated efficiency by −0.000137 percentage points. |
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
