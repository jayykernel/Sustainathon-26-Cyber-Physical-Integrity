# Public measured-cell data validation

## Cell-held-out check: CS2_33 to CS2_34

To test generalization across physical units, the one-RC model was fitted using
150 earlier cycles from CALCE cell CS2_33 and scored on all 775 usable discharge
cycles from the separate CS2_34 cell. Both cells are listed by CALCE as 1.1 Ah
LiCoO2 CS2 cells cycled at 0.5C. The archive SHA-256 values are
`ce375e3826e840ff0986ceade0d324ba6515f0446697c947353aca097f232505` for
CS2_33 and `229dcdc836f140f746c26316569c357b346994fddd3be1223b1e457805c484b4`
for CS2_34.

Download both checksum-pinned public archives and extract them under
`data/raw/calce/` with:

```powershell
backend\.venv\Scripts\python.exe scripts\download_calce.py
backend\.venv\Scripts\python.exe scripts\validate_twin_calce_cross_cell.py
```

The CS2_34 test cell is excluded from fitting. The test RMSE is 0.0919 V, MAE
0.0691 V, and p95 absolute error 0.1761 V over 77,435 decimated measured voltage
samples. The result is recorded in
`data/results/calce_cross_cell_33_to_34.json`; the figure is
`data/results/calce_cross_cell_33_to_34.svg`. This improves the evidence over
one-cell-only evaluation, but still uses measured per-cycle capacity to
construct reference SOC and covers only two small cells of one chemistry and
one nominal cycling rate. It is not validation of a pack, temperature model,
attack detector, BMS, vehicle, or safety response, and no deployment acceptance
limit has been established.

## CALCE CS2_33 voltage-model experiment

The project had no measured battery data under `data/raw/`; the original NASA
P1b result therefore remained unavailable. To begin the user's requested
real-data check, this experiment uses CALCE's publicly listed CS2_33 test files.
The archive is downloaded locally to the ignored `data/raw/calce/` directory
and is not committed. Source: <https://calce.umd.edu/battery-data>,
<https://web.calce.umd.edu/batteries/data/CS2_33.zip>.

The CALCE page describes CS2 as a 1.1 Ah LiCoO2 prismatic cell tested with
CC/CV charging and multiple cycling protocols. The selected CS2_33 records
contain measured time, current, voltage, and discharge-capacity columns. The
archive SHA-256 is
`ce375e3826e840ff0986ceade0d324ba6515f0446697c947353aca097f232505`.

Download and checksum-verify the archive, then run the experiment:

```powershell
backend\.venv\Scripts\python.exe scripts\download_calce.py CS2_33
backend\.venv\Scripts\python.exe scripts\validate_twin_calce.py
```

The script fits a monotone OCV curve and a one-RC voltage model on up to 150
evenly sampled cycles from the first 70% of the chronological records. It scores
all later cycles and writes `data/results/calce_cs2_33_validation.json` plus a
representative SVG trace. CALCE's capacity field is cumulative across cycle
records, so the loader subtracts each cycle's first recorded discharge capacity
before deriving a reference SOC. This check uses delivered capacity from each
measured test cycle as reference SOC; it is not available as ground truth in a
vehicle.

### Recorded outcome

The chronological held-out experiment measured a training-cycle voltage RMSE
of 0.0563 V and a later-cycle test RMSE of 0.1916 V (test MAE 0.1408 V; 95th
percentile absolute error 0.4069 V), across 248 held-out cycles. The increase in
held-out error is material. No acceptance threshold was specified in the plan,
so these values do not pass a stated criterion and must not be presented as
evidence that the model is sufficiently accurate for vehicle use. The fitted
cell-specific parameters are exploratory outputs, not replacements for the
60 Ah prototype configuration.

This dataset has one small lab cell, no vehicle pack, no time-series cell
temperature, no BMS or CAN traces, and no labeled cyberattacks. It cannot
validate pack thermal behavior, the anomaly detector, localization, command
guard, driver response, or emergency actions. It does not establish Tesla or
EV compatibility or deployment readiness. A materially better experimental
program needs independent cells and packs, multiple chemistries and ages,
environmental conditions, representative charge and drive profiles, calibrated
temperature instrumentation, and an independent test split across physical
units—not only cycles from one cell.

## Remaining real-world evidence required

- Public cell data can check portions of the electrical model. It cannot
  substitute for OEM/BMS telemetry or a physical pack.
- Before any vehicle connection, specify the target BMS/vehicle, authorized
  signals, read/write permissions, and the OEM-approved interface. No Tesla
  interface or vehicle connection exists in this repository.
- Test in replay/HIL first, then an isolated instrumented pack on a controlled
  dynamometer or battery test rig with independent hardware limits and a
  qualified safety engineer. Validate sensor faults, model mismatch, false
  alarms, detection latency, containment behavior, watchdog/reset failures,
  stale/lost communications, and deterministic safe fallback.
- The simulator's deterministic probe-key fallback is for reproducibility only.
  Real integration requires hardware-backed secret provisioning, storage,
  rotation, access control, and a threat analysis of key compromise. The local
  alert endpoint only acknowledges/logs a request; it is not an emergency
  communications channel. The API has no production authentication or TLS
  configuration and must not be exposed to a vehicle or public network.
- Keep all control actions advisory until a separate functional-safety case,
  cybersecurity risk process, OEM integration review, and applicable
  jurisdictional type-approval evidence authorize anything more. UN R155/R156,
  UN R100, ISO 26262, and ISO/SAE 21434 are relevant workstreams; this codebase
  does not demonstrate compliance or certification.
