# DEMO_SCRIPT.md

Three-minute dashboard demo, then Q&A. Rehearse before submission. Read live values from the active run and benchmark values from the backend report; never estimate a number.

## Setup checklist (5 minutes before)
- Start the backend and primary `static-website` frontend using the root README instructions. The browser UI should show **Backend ready**.
- Keep the network available for the live API/WebSocket demo. Offline replay is a separate recorded-data path and must be labeled as such.
- Select `baseline`, set seed `4242`, choose 20×, then start a live run. Use the classifier, chart, response posture, and event log as the walkthrough.

## Script (3:00)

**0:00–0:25 Scope.** "PhysiGuard is a simulation bench for battery telemetry integrity. It compares measured signals with a cell-model estimate and records how different detector and response configurations behave under defined simulated attacks. This is not connected to a real vehicle."

**0:25–0:50 Baseline run.** Start the baseline and point to the live clock, current, state, and channel. "These values come from the backend's live simulation stream. The chart compares physical truth, reported telemetry, and the model estimate. This is simulated, not an onboard vehicle measurement. A clean run can still produce a temporary SUSPECT warning; the alert says that alone does not prove malware."

**0:50–1:20 Inject an attack.** Select a defined attack channel, inject it into the running simulation, and point to the event log and classifier. "The backend records the injection and streams the resulting telemetry. Detection is not guaranteed for every attack; the benchmark table shows measured detection and false-alarm results by configuration."

**1:20–1:55 Compare signals.** Point to reported, estimated, and true telemetry, plus NIS/CUSUM/probe/localization values. "A model-aware attacker is difficult: B2 detected AT4 in 27.5% of validation runs. Adding the probe did not make this reliable. We show that limitation rather than claim universal detection."

**1:55–2:25 Response and limitations.** Point at response posture and current limit. "The software simulation can enter a conservative response state and use its virtual sensor. That is a simulated control result; it is not a command to a charger or car. The prototype needs independent hardware-in-the-loop and pack testing before any real control action."

**2:25–2:50 Benchmarks.** Open the detector evaluation table. "These are held-out simulation results on seeds 1000–1199. B3 reports 0.160 baseline false-alarm episodes per hour against the 0.20 target, but B3 detects AT4 in 19.5% and AT6 in 15.5%, and it trails B2 on several attacks. The full evaluation took 695.6 seconds, still above the ten-minute gate. These limits matter for deployment decisions."

**2:50–3:00 Close.** "The contribution is an evaluated physical-consistency signal and a conservative simulated response. Real-world validation remains open: independent cells and packs, calibrated temperature sensing, target BMS integration, and hardware-in-the-loop safety testing."

## If something breaks
| Failure | Action |
|---|---|
| Backend not reachable | UI offers "Replay a recorded run". Say: "This is a recorded run from the same simulator." Continue script. |
| Browser glitch | Reload; state is deterministic by seed. |
| Everything fails | Play backup video; run Benchmarks page from static results if available. |

## Likely questions (answer from evidence; fill brackets from results)
1. **Is this real data?** The live demo is simulated. A separate exploratory CALCE single-cell voltage-model check had 0.1916 V RMSE on later cycles, using measured discharge capacity as reference SOC. It does not validate temperature, attacks, pack behavior, BMS, or vehicle safety. No NASA validation or hardware integration exists.
2. **Why use a physics model?** It provides an explicit voltage/temperature reference for this experiment. The project has not shown superiority to machine-learning approaches; no ML model was shipped.
3. **What protects the probe?** It uses a keyed, fresh-per-window sequence in the simulation. An attacker with access to the true command/current path can defeat the assumption; this limitation is reported.
4. **Does the probe harm the battery?** Only simulated overhead was measured across 20 paired runs: peak temperature +0.0118 °C, final temperature +0.0020 °C, time to 90% SOC +1.25 s, and estimated efficiency −0.000137 percentage points. This is not a physical battery safety result.
5. **How were false alarms measured?** The passive detector's earlier held-out check on seeds 100–199 produced 0.2101 episodes/hour. In the updated full evaluation, B3 produced 0.160 episodes/hour on seeds 1000–1199 (B2: 0.135/hour). A direct state audit found 30/200 honest baseline runs entered SUSPECT, 27 cleared, none reached CONFIRMED or SAFE_MODE, and three stayed SUSPECT through the hour. These are simulation results, not a physical false-alarm rate.
6. **Were thresholds tuned on the test set?** No. Calibration and test seeds are separated; the evaluation includes a regression check for the split.
7. **How good is localization?** On validation seeds 0–99, the temperature channel was correctly localized in 100/100 AT1 runs and 85/100 AT2 runs; AT2 had 5 unknown results and 10 runs with no localization output.
8. **How does the model-aware attack perform?** It is a difficult case, not a solved one: B2 detected AT4 in 27.5% of validation runs. The 4% probe's combined gain detector caught 3%; it does not reliably close the gap.
9. **Does it scale to a pack or fleet?** Not demonstrated. The CALCE experiment uses one small lab cell, and the simulator's pack behavior has no independent pack validation.
10. **What about aging and temperature drift?** The CALCE split shows weaker voltage fit on later cycles. Temperature channels and pack-level thermal aging have not been validated.
11. **Where is the AI?** No learned model is included. The prototype uses a physical model, an EKF, statistical detectors, and a command guard.
12. **Is this compliant with vehicle cybersecurity or safety standards?** No compliance, certification, or standards-conformance claim is made. A qualified engineering and regulatory process is required before vehicle deployment.

## Recording shot list (backup video)
1. Show dashboard and scope note (10 s). 2. Run baseline and inject a defined attack (90 s). 3. Show detector metrics and measured limitations (30 s). 4. Show method and limits, ending on the real-hardware validation gap (10 s). Record only after a live browser smoke succeeds.
