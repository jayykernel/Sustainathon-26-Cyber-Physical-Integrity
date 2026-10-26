# SPEC.md — PhysiGuard technical specification

Source of truth for backend behavior. Parameter values here are **starting values**; tune them in the phase named, then record final values in `configs/default.yaml` and log the change in PROGRESS.md.

Conventions: SI units, temperature in °C, current > 0 = charging, time step `dt = 1 s`, simulation length 3600 s unless stated.

---

## 1. Threat model and trust boundaries

```
 upstream request I_req ──► [COMMAND GUARD] ──► charger power stage ──► BATTERY (true plant)
        ▲ (attack: malicious command)               ▲ probe δI added here          │
                                                    │                              ▼
                                           GUARD (trusted)                   sensors (V, I, T)
                                                    ▲                              │
                                                    └───── telemetry path ◄────────┘
                                                      (attack: spike, drift, replay,
                                                       model-synthesis spoofing)
```

Trusted: the guard process, its probe key, the commanded current it issues (`I_cmd`, including the probe).
Untrusted: the telemetry path (V, I, T reports) and the upstream request `I_req`.

Attacker capability levels (all evaluated and reported):

| Level | Knows | Does | Expected outcome |
|---|---|---|---|
| A0 blind | nothing about the detector | spike, drift | caught by passive tests |
| A1 model-aware | twin structure, nominal parameters, thresholds, past telemetry. **Not** the probe key or `I_cmd` in real time | synthesizes plausible telemetry (model-synthesis), replays | passive tests miss; active verification should catch |
| A2 oracle | everything in A1 **plus** real-time `I_cmd` including probe | synthesizes telemetry containing the probe response | **expected to defeat active verification. Report as a limit.** |

Out of scope (state in Limits view): compromised guard, key theft, physical sensor tampering that is physically real, multi-cell pack effects, aging, real hardware.

---

## 2. Plant (ground truth simulator)

The plant is **deliberately more detailed than the twin** so the twin has realistic model mismatch.

State: `SOC, V1, V2, T` (two RC pairs + lumped thermal).

```
OCV(SOC): monotone piecewise-linear table, SOC = 0.0..1.0 step 0.1
          [3.00, 3.30, 3.45, 3.55, 3.62, 3.68, 3.75, 3.82, 3.92, 4.05, 4.20]  (V, generic NMC)
SOC[k+1] = SOC[k] + eta * I[k] * dt / (3600 * Q)            eta = 0.995 charging
V1[k+1]  = V1[k]*exp(-dt/tau1) + R1*(1-exp(-dt/tau1))*I[k]
V2[k+1]  = V2[k]*exp(-dt/tau2) + R2*(1-exp(-dt/tau2))*I[k]
R0(T)    = R0_ref * (1 + a_R * (25 - T))                    a_R = 0.012 /°C
P_heat   = I^2 * (R0(T) + R1 + R2)
T[k+1]   = T[k] + dt/C_th * ( P_heat - (T[k] - T_amb[k]) / R_th_eff )
V_term   = OCV(SOC) + I*R0(T) + V1 + V2
```

Starting parameters (generic 60 Ah prismatic cell, ~1 kg, passive cooling):
`Q=60 Ah, R0_ref=1.2 mΩ, R1=0.6 mΩ, tau1=30 s, R2=0.5 mΩ, tau2=160 s, C_th=800 J/K, R_th=2.5 K/W (thermal time constant 2000 s), T_amb=35 °C (hot-day scenario) with slow drift ±1.5 °C/h, initial SOC=0.10, initial T=T_amb`.
Sanity: at 90 A the ohmic+RC drop is about 0.21 V and heat is about 19 W, so the steady-state rise is about 46 K at constant 90 A.

Unit-to-unit variation (seeded per run): `Q ±3%, R0 ±10%, R1 ±10%, R_th ±10%, OCV table offset ±10 mV`.

Hazard events (any of these is a simulated hazard): `T_true > T_hazard = 55 °C`, `V_true > V_hazard = 4.30 V`, `SOC_true > 1.02`. Other limits: derate window 40–50 °C on **reported** T, `T_warn = 50 °C`, `V_max = 4.20 V`, `V_min = 3.00 V`, rated current limit `3C = 180 A`. Plant SOC is allowed above 1.0 (OCV clipped at 4.20 V) so overcharge is observable.

**Sensors**: `V: σ=8 mV`, `I: σ=0.15 A`, `T: σ=0.10 °C`, 1 Hz, quantization V 1 mV / I 0.01 A / T 0.01 °C. Noise is Gaussian from a seeded generator.

**Upstream profile controller** (produces `I_req`): fast charge at 1.5C = 90 A until `V_term ≥ V_max`, then CV taper (proportional controller on V). **Charger** (executes requests): `I_cmd = min(I_req, 180 A) × f_thermal(T_rep)` where `f_thermal` falls linearly from 1.0 at 40 °C to 0.2 at 50 °C using the **reported** temperature. The charger does **not** run its own CV loop; it trusts the upstream request. This is the naive-but-realistic logic the attacks exploit: false `T_rep` defeats the derate, and a hijacked `I_req` defeats the CV taper.

**P1 plausibility targets** (verify, tune parameters until true, then freeze):
1. Honest 60-min run, 35 °C ambient: `T_true` stays below `T_warn` (expected equilibrium near 46–48 °C under derating), SOC rises monotonically, V stays within [V_min, V_max+0.02].
2. If `T_rep` is held at 30 °C (under-reported) so derating never engages, `T_true` exceeds `T_hazard` within about 25 minutes. If not, adjust `R_th`/`C_th`/`I_req` until it does (the hazard must be reachable for the demo to mean anything). Likewise a hijacked request of 150 A during the CV phase must push `V_true` above `V_hazard` or `SOC_true` above 1.02 within 5 minutes.
3. Analytic check: constant current steady-state temperature rise equals `I²(R0+R1+R2)·R_th` within 1% (unit test with long horizon and fixed T-independent R0).

---

## 3. Twin and EKF

Twin (what the guard knows), 1-RC:

```
x = [SOC, V1, T]
SOC' = SOC + eta*I*dt/(3600*Q_n)
V1'  = V1*e^(-dt/tau1) + R1_n*(1-e^(-dt/tau1))*I
T'   = T + dt/C_th_n * ( I^2*(R0_n+R1_n) - (T - T_amb_hat)/R_th_n )
y_pred = [ OCV_n(SOC) + I*R0_n + V1 ,  T ]
```

Nominal twin parameters `*_n` are the plant nominal values with the 2-RC dynamics lumped into R1 (`R1_n = R1+R2`, `tau1_n` ≈ 60 s, to be fitted in P1 by least squares on plant-generated attack-free data). `T_amb_hat` is a configured constant (guard has no ambient sensor) so it is another source of mismatch.

EKF: `F = diag-block` with `dOCV/dSOC` in `H`. Process noise `Q_ekf` and measurement noise `R_ekf = diag(σ_V², σ_T²) * inflation`, `inflation` tuned on **validation** data so that NIS is approximately chi-square. Input `u = I_cmd` (trusted). Initialization: SOC from inverse OCV of first V sample; large initial covariance on SOC.

Joseph-form covariance update; symmetrize `P` each step; guard against singular `S` (raise typed error, never NaN-propagate). Unit tests: on a synthetic **linear** system with known noise, NIS mean ≈ m and NEES consistent (chi-square bounds), EKF reduces to the Kalman filter.

Current-consistency residual (separate third channel): `r_I = I_rep − I_cmd`, `σ_I` from the sensor + actuator tracking noise (config).

---

## 4. Passive detection

All residuals are standardized: `z_V = ν_V/√S_VV`, `z_T = ν_T/√S_TT`, `z_I = r_I/σ_I`.

- **NIS window test**: `NIS_k = νᵀ S⁻¹ ν`; windowed sum over `L = 30 s`; alarm if above threshold `θ_NIS`.
- **CUSUM** per channel, two-sided: `g⁺ = max(0, g⁺ + z − κ)`, `g⁻ = max(0, g⁻ − z − κ)`, `κ = 0.5`; alarm if `max(g⁺,g⁻) > h`; reset after alarm. Optional dead-band so model mismatch does not accumulate.
- **Range baseline (B0)**: static limits on V, I, T and a rate limit on T (`|dT/dt| ≤ 0.5 °C/s`).

**Calibration** (`make calibrate`): run attack-free validation seeds (0–99). Empirical thresholds, not theoretical ones, set per test so each gets an equal share of the total false-alarm budget (`FA_target = 0.2 alarms per simulated hour` combined). Write to `configs/detection.yaml` with metadata (seeds, config hash, date). The chi-square distribution is used as a **diagnostic** (QQ check), not as the threshold source, because model mismatch breaks the assumption. Say this honestly in the Method view.

---

## 5. Active verification (probe / watermark)

**Probe**: zero-mean PRBS δI ∈ {+a, −a}, chip length 5 s, generated from a keyed PRNG (`numpy.random.Generator(PCG64(seed=HMAC-SHA256(key, nonce)))` — nonce fresh per challenge window; key from env var, with a random per-process fallback for demos). Amplitude `a = 4%` of `I_req` by default (config), additionally clipped so `I_cmd + δI` respects `V_max` and thermal limits. Net charge ≈ 0.

**Schedule**: challenge window `W = 120 s` every `P = 600 s` in NORMAL; continuous probing in SUSPECT/CONFIRMED/SAFE_MODE.

**Test (probe gain)**: from the window of reported voltage `V_rep` and reported current `I_rep`:
1. Compute expected probe response `s_k` = twin impulse response convolved with the issued δI (sensitivity of `y_V` to δI).
2. High-pass filter (e.g., subtract 60 s moving average) both `V_rep` and `s_k` to remove slow state dynamics and model mismatch.
3. Gain estimate `ĝ_V = Σ V_hp·s_hp / Σ s_hp²`, standard error `σ_g = σ_V,eff / √(Σ s_hp²)`.
4. Authentic telemetry → `ĝ ≈ 1`. Replay / model-synthesis spoof (no knowledge of the probe) → `ĝ ≈ 0`.
5. Alarm if `ĝ < g_min`, where `g_min` is calibrated on attack-free validation windows at the allotted FA budget. Same for `ĝ_I`. Report ĝ values in the UI.

**Required figure** (P5/P7): detection rate versus probe amplitude (0.5%–8% of `I_req`) for (a) passive EKF+CUSUM driven by `I_cmd` with the probe present and (b) the gain test. This shows where passive fails and the active test recovers detection, and gives the honest overhead tradeoff.

**Channel reporting**: the probe also appears in the reported current (`I_rep` should track `I_cmd`), so the current-channel gain test is expected to dominate at large amplitudes. Evaluate and report **V-only**, **I-only**, and combined gain tests so the physics-based voltage test is not hidden behind the trivial current check. Default amplitude `a = 4%` of `I_req` (about 3.6 A, giving roughly 4–5 mV on V against 8 mV noise, i.e., sub-noise per sample and detectable only through accumulation over the window).

**Overhead measurements** (report): extra heating (ΔT_true at end), charge-time delta, energy efficiency delta versus no-probe, over attack-free runs.

A2 (oracle) attacker includes the true δI in its synthesized telemetry. Expect the gain test to fail; report.

---

## 6. Attacks (`configs/attacks.yaml`, frozen at P3 gate)

Each attack implements `apply(t, truth, reported, rng, ctx) -> reported'` and optional `physical(t, plant)` / `request(t, I_req)` hooks. All attacks have: `onset` (random in [600, 1500] s per seed unless set; AT5 uses its own rule), `duration` (default until end), and a documented knowledge level.

| ID | Name | Mechanism | Physical consequence path |
|---|---|---|---|
| AT1 | spike | `T_rep += Δ` for short bursts (Δ=10–20 °C) plus `V_rep` glitches; some below range limit | brief false derate; mostly a detectability sanity check |
| AT2 | slow drift | `T_rep -= ρ·(t − onset)`, `ρ` = 0.5 °C/min (far below per-sample noise, so per-sample tests cannot see it) | controller keeps charging because `T_rep` looks cool → real T climbs |
| AT3 | replay | from onset, telemetry = recorded attack-free telemetry from `Δt` earlier, looped; **plus** physical payload: cooling degradation `R_th × 2.5` from onset | masks real overheating |
| AT4 | model-synthesis (A1) | attacker runs its own twin (nominal params + configurable model error) driven by the nominal request profile **without** the probe; reports `V,I,T` = twin output + matched noise; **plus** the same cooling-degradation payload | masks real overheating; passive tests see consistent data |
| AT5 | malicious command | from onset (first time `SOC_true ≥ 0.85` plus 0–120 s random delay, i.e., CV phase) upstream `I_req` is forced to 150 A (2.5C, below rated 3C, so every range check passes); telemetry honest | overvoltage / overcharge (`V_true > 4.30 V` or `SOC_true > 1.02`) because the charger has no CV loop of its own |
| AT6 | oracle (A2) | AT4 with the true `I_cmd`/δI included | limit case |

Stealth requirement (checked in P3 tests, reported): AT4 must **not** be reliably caught by B1 (EKF-NIS) and B2 (EKF+CUSUM) with no probe; AT2 must be missed by B1 at its tuned FA but caught by B2 over a measurable delay; AT1 caught by B2. If AT4 is caught by B2 >90% without probe, the attack is too weak: fix the attack (not the metric) and log it.

---

## 7. Localization (AI-07)

Per-channel cross-prediction residuals, computed over a sliding window `L_loc = 60 s`:
- full EKF (V,T) → `z_V`, `z_T`;
- V-only EKF predicts T → `e_T|V`; T-only EKF predicts V → `e_V|T`;
- current: `z_I`.

Rule: blame the channel with the dominant standardized score if its score exceeds the next by factor `ρ_dom` (config, tuned on validation); if two or more channels exceed threshold with no dominance output `multi`; if the alarm fires without channel evidence output `unknown`; for command-guard events output `command`. Output: `{channel ∈ {v,i,temp,multi,command,unknown,none}, confidence ∈ [0,1], evidence{...}}`.

Report a confusion matrix per scenario, with `multi` counted as correct for AT3/AT4/AT6 (all telemetry channels forged) and as ambiguous otherwise. State this scoring rule in the Benchmarks view.

---

## 8. Command guard, response, virtual sensors

**Command guard** (before actuation): forward-simulate the twin with **pessimistic** parameters (`R_th×1.5, T_amb+5 °C, R0×1.2`) over horizon `H = 300 s` using `I_req`. If predicted `V > V_max`, `T > T_warn`, or `SOC > 1.0`: flag `cmd_unsafe`, compute `I_safe(t)` = largest current (bisection, ≤8 iterations) that keeps the prediction safe; apply `I_cmd = min(I_req, I_safe)`.

**State machine** (hysteresis):
`NORMAL` → `SUSPECT` (any single evidence) → `CONFIRMED` (≥2 independent evidence classes within 60 s, or probe failure in 2 consecutive windows, or `cmd_unsafe` with prediction violation) → `SAFE_MODE` (CONFIRMED persists 10 s). Return to NORMAL only after `N_clean = 3` consecutive clean challenge windows **and** operator reset (button in UI). Evidence classes: passive-NIS, CUSUM, probe-gain, command-unsafe.

**SAFE_MODE actions**: (1) `I_cmd = min(I_cmd, I_safe_worst)` where `I_safe_worst` keeps `T` below `T_warn` even with cooling degradation `R_th×4`, and `V` below `V_max`; (2) controller uses virtual `T` instead of `T_rep`; (3) continuous probing; (4) event emitted.

**Virtual sensors**: EKF estimates using only channels not flagged. If all telemetry channels are suspect (AT3/AT4/AT6), run open-loop twin with pessimistic parameters and mark estimate quality `degraded`. Be explicit in the UI that virtual T under cooling degradation is a **bound**, not an accurate value.

---

## 9. Evaluation protocol

- Seeds: calibration/validation 0–99; test 1000–1199. Never mix. Attack parameters frozen before calibrating defender thresholds.
- Test set: 200 attack-free runs (200 simulated hours) for false alarms; ≥200 runs per attack scenario.
- Detectors (all evaluated on the same runs): **B0** range, **B1** EKF-NIS, **B2** EKF-NIS+CUSUM, **B3** full (B2 + probe gain + command guard + localization + response). B0–B2 run **without** the probe injection (that is what a passive monitor is). Also an ablation: **B2+probe-present** (passive tests with the probe active) to separate "probe present" from "gain test".
- Alarm episode merging: alarms within 60 s are one episode. False alarm = episode on attack-free run (or before onset).
- Metrics per (detector, scenario): detection rate with Wilson 95% CI; detection delay (median, IQR) from onset; **safety margin at detection** = `T_hazard − T_true(t_detect)` (thermal attacks) or `V_hazard − V_true(t_detect)` (AT5); peak `T_true`; peak `V_true`; hazard-event rate (any of the three hazard events); **hazard reduction** (B3 closed-loop vs undefended, paired by seed) = reduction in peak `T_true`/`V_true` and in hazard-event probability; localization confusion matrix; false alarms per hour with CI.
- Outputs: `data/results/results.json` (schema-validated), `results.csv`, `tables.md`, figures (`.svg`), `meta.json` (git hash, config hash, seeds, date, runtime).
- `make eval` must be bit-for-bit repeatable (same inputs → same `results.json` apart from `meta.json` timestamp). Test this.
- No numeric "pass" thresholds on detection performance (results are what they are). Sanity expectations (bugs if violated, not tuning targets): AT1 large spikes detected by B3 ≥95%; B0 false alarms ≈ 0; B3 never worse than B2 on telemetry attacks at equal FA.

**Stretch S1 (ML residual learner, COULD)**: ridge or gradient-boosting model predicts voltage-model mismatch from `[SOC, I, T, V1]`, trained on validation seeds only, added to EKF prediction. Include ablation (with/without) and only claim it if it improves FA or detection on **test** seeds with CI reported.

---

## 10. API contract

Base `/api`. All bodies validated by pydantic. Errors: `{ "error": { "code": str, "message": str } }`, HTTP 4xx/5xx; never a stack trace.

REST:
- `GET /api/health` → `{status, version, config_hash, thresholds_loaded}`
- `GET /api/scenarios` → list of `{id, title, description, attack, level, story_steps[]}`
- `POST /api/sessions` `{scenario_id, seed?, speed?}` → `{session_id}` (max 4 concurrent, idle timeout 15 min)
- `GET /api/sessions/{id}` → status; `DELETE /api/sessions/{id}`
- `GET /api/benchmarks` → contents of `results.json` + `meta.json` (or 404 `benchmarks_missing` with a clear message)
- `GET /api/limits` → static threat model and limitations content (single source for the Method/Limits view)

WebSocket `/api/sessions/{id}/ws`:
- Server → client: `hello {version, config_hash, scenario}`, `frame_batch {frames[]}` (≤10 batches/s; each batch contains `speed` steps decimated to ≤ 10 frames), `event {t, kind, severity, text, data}`, `done {summary}`, `error {code, message}`.
- Client → server: `inject {attack, params?}`, `pause`, `resume`, `speed {value ∈ 1,5,20,60}`, `reset {seed?}`, `operator_reset`.

Frame:
```json
{ "t": 1234,
  "truth": {"soc":0.61,"v":3.98,"i":88.1,"temp":47.2},
  "truth_undefended": {"soc":0.61,"v":3.99,"i":90.0,"temp":58.9},
  "reported": {"v":3.98,"i":88.0,"temp":38.1},
  "predicted": {"v":3.98,"temp":47.0,"soc":0.60},
  "residual": {"v":0.2,"i":0.1,"temp":-9.3},
  "evidence": {"nis":4.1,"nis_thr":11.0,"cusum":{"v":0.3,"i":0.0,"temp":7.9},"cusum_thr":6.0,
               "probe":{"active":true,"gain_v":0.04,"gain_i":0.02,"gain_min":0.5},"cmd_unsafe":false},
  "state": "CONFIRMED",
  "localization": {"channel":"temp","confidence":0.82},
  "control": {"i_req":90.0,"i_cmd":42.0,"i_safe":42.0,"mode":"derated"},
  "margins": {"temp":12.8,"v":0.21},
  "attack": {"active":true,"name":"drift","onset":900} }
```
`truth_undefended` is the paired plant (same seed, same attack, no defense). It exists so the UI can show the counterfactual. Both plants are advanced in the same session loop, deterministically.

Frontend offline mode: if the backend is unreachable, the UI loads `frontend/public/demo-runs/<scenario>.json` (recorded frames from `make demo-data`) and replays them with a visible "Replay of a recorded run" banner. Nothing in replay mode may be presented as live.

---

## 11. Logging, errors, performance budgets

- Python `logging` with JSON formatter; session ids in log context.
- Typed exceptions: `ConfigError, ModelError, NumericalError, SessionError`. API maps them to codes.
- A single session step < 2 ms average (target) so 60× speed is sustainable; 4 concurrent sessions must not degrade the 1× experience.
- `make eval` < 10 min on a laptop (use `multiprocessing`, deterministic per-run seeds).
- Frontend: keep ≤ 900 points per chart series (rolling window with decimation); no animation on streaming series.
