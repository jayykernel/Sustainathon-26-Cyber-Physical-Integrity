# CLAIMS_EVIDENCE.md

Every claim in the submission text must map to evidence produced by the repository. Status values: `unverified` (default), `supported`, `softened` (text changed to match), `removed`. Claude updates this file; the user approves the final text.

Rule: if evidence does not exist at P11, the claim is softened or removed. Do not build evidence to fit a claim after seeing results.

| # | Claim in submission text | Evidence (file / command) | Status | Final wording or note |
|---|---|---|---|---|
| 1 | Digital twin of battery electrical and thermal behavior | `backend/src/physiguard/twin.py`, tests | softened | A simulated equivalent-circuit model estimates cell voltage and temperature; its thermal behavior and EV-pack accuracy are not validated on real hardware. |
| 2 | Twin calibrated and evaluated on public datasets (NASA/CALCE) | `scripts/validate_twin_calce.py`, `backend/src/physiguard/eval/calce_validation.py`, `data/results/calce_cs2_33_validation.json`, `docs/DATA_VALIDATION.md` | softened | One exploratory CALCE CS2_33 cell-voltage experiment was run: chronological held-out RMSE was 0.1916 V versus 0.0563 V on fit cycles. No NASA validation, EV-pack, thermal, BMS, cyberattack, or vehicle-response validation exists; this experiment does not establish deployment accuracy. |
| 3 | EKF with innovation-based chi-square testing | `backend/src/physiguard/ekf.py`, `backend/src/physiguard/detectors/nis.py`, `data/results/nis_qq.json` | softened | The EKF uses NIS as an innovation diagnostic; thresholds are empirically calibrated and do not establish chi-square calibration on physical vehicle data. |
| 4 | CUSUM catches gradual drift | `data/results/stealth_report.json` AT2 B1 vs B2 | supported | On validation seeds 0–99, B1 caught 32% and B2 caught 90%; B2 median delay among detections was 1165.5 s. |
| 5 | Residual signatures localize the suspected channel | `data/results/localization_report.json` AT1/AT2 confusion matrices | supported | On validation seeds 0–99, temp-dominant localization was correct for 100/100 AT1 runs and 85/100 AT2 runs; 5 AT2 runs were unknown and 10 had no localization output. |
| 6 | Thresholds calibrated on attack-free validation data; false alarms measured on separate test data | `configs/detection.yaml`, `data/results/passive_fa_validation.json`, `data/results/passive_fa_test.json` | softened | Thresholds were calibrated on seeds 0–99. Held-out seeds 100–199 produced 0.2101 false alarms/hour, slightly above the 0.20/hour target; do not claim the test target was met. |
| 7 | Active random probe exposes replay and model-aware attacks that passive monitoring misses | `data/results/probe_report.json`, `data/results/probe_amplitude_sweep.svg` | softened | At 4% amplitude, active gain detects AT3 on 100% of validation runs, but detects AT4 on 3% combined versus 27% B2 without probing (29% B2-with-probe). The probe does not establish improved AT4 detection. |
| 8 | We test against model-aware attackers | AT4 definition in `configs/attacks.yaml`; `data/results/stealth_report.json` | supported | AT4 is a no-command/no-probe model-synthesis attacker; B2 caught 27% on validation seeds 0–99. |
| 9 | Virtual sensor estimates and conservative charging reduce simulated hazard | `data/results/p6_closed_loop_report.json`, `data/results/p6_closed_loop_summary.md`; virtual sensor tests | supported | On paired validation seeds 0–9, mean peak temperature and voltage were lower for AT2–AT5. Hazard rates changed AT2 0%→0%, AT3 30%→0%, AT4 0%→0%, and AT5 100%→0%. This is simulated evidence on 10 seeds. |
| 10 | Malicious but valid commands are blocked | AT5 rows in `data/results/p6_closed_loop_report.json`; `backend/tests/test_response.py` command guard coverage | supported | Across validation seeds 0–9, the undefended AT5 runs reached a hazard in 10/10 cases; defended runs reached a hazard in 0/10. |
| 11 | Reproducible red-team vs blue-team experiments | `backend/tests/test_evaluation.py`, `data/results/meta.json` | supported | The reduced evaluation repeatability test compares serialized results; reproducibility is for this simulation/configuration, not a physical test bench. |
| 12 | Baseline comparison: range-based, EKF-only, EKF+CUSUM, full | `data/results/results.json`, `data/results/tables.md`, `data/results/meta.json` | softened | On held-out seeds 1000–1199, B3's baseline false-alarm rate was 0.160/hour (below the 0.20/hour target but higher than B2's 0.135/hour). B3 detections were lower than B2 for AT2, AT3, AT4, and AT6; it performed strongly on AT1 and AT5. Report this as a measured comparison, not an overall improvement. Evaluation runtime was 695.6 s, above the 600 s gate. |
| 13 | Probe overhead is small | overhead table in `data/results/probe_report.json` | supported | Across 20 paired validation runs, mean peak temperature changed by +0.0118 °C, final temperature by +0.0020 °C, time to 90% SOC by +1.25 s, and estimated efficiency by −0.000137 percentage points. |
| 14 | Addresses AI-01, AI-07, AI-10 | rows 4–5, 9; `data/results/` | softened | The prototype explores detection, localization, and simulated cyber-to-physical impact relevant to the named problem areas; no external problem-statement assessor has certified that mapping. Do not claim AI-08. |
| 15 | Complements UN R155 / ISO/SAE 21434 practices | none (positioning statement) | removed | Do not state standards alignment, compliance, certification, or complementarity without a qualified mapping and review. |
| 16 | Extends to chargers, fleets, stationary storage | none (future work) | softened | Other platforms are possible future research; no extension has been demonstrated. |
| 17 | Learned/ML component (if mentioned anywhere) | S1 residual learner was not implemented | removed | No ML component is included or claimed. |

## Claims at risk (Claude adds items here during the build)
- Combined passive false alarms measured 0.2101/hour on held-out attack-free seeds, slightly above the 0.20/hour target. This is reported without retuning on test data.
- Updated full detector evaluation meets the baseline FA target (B3 0.160/hour) but not the runtime gate and not the SPEC B3-vs-B2 telemetry-attack sanity expectation; AT4 and AT6 detection remain low. The UI shows the measured run, including its limitations. No test-seed tuning was performed.

## Tech stack text must match
- Remove `filterpy` (EKF is in-repo).
- Include `scikit-learn` only if S1 shipped.
- Include `PyBaMM` only if actually used (default plan: custom equivalent-circuit model).
- Primary frontend: TypeScript, Vite, Three.js, native DOM/CSS. The separate React `frontend/` directory is not served by the normal launcher. Backend: Python, NumPy, SciPy, FastAPI, Pydantic. Do not describe the selected stack as React/Tailwind/ECharts/Zustand.

## Final submission text
(Claude writes the final version here in P11 after all rows are resolved. The user pastes it into the form.)
