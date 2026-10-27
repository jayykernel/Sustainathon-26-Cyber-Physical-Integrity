"""Fit a CALCE model on CS2_33 and test it on the separate CS2_34 cell."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from physiguard.eval.calce_validation import (
    DischargeCycle,
    FitResult,
    fit_voltage_model,
    load_dataset,
    load_discharge_cycles,
    predict_cycle_voltage,
)

ROOT = Path(__file__).resolve().parents[1]
CALCE_DIR = ROOT / "data" / "raw" / "calce"
TRAIN_ARCHIVE = CALCE_DIR / "CS2_33.zip"
TEST_ARCHIVE = CALCE_DIR / "CS2_34.zip"
REPORT = ROOT / "data" / "results" / "calce_cross_cell_33_to_34.json"
FIGURE = ROOT / "data" / "results" / "calce_cross_cell_33_to_34.svg"


def _test_cycles() -> list[DischargeCycle]:
    files = sorted((CALCE_DIR / "CS2_34").glob("*.xlsx"))
    if not files:
        raise FileNotFoundError(f"Extract CS2_34.zip under {CALCE_DIR}")
    cycles = [cycle for path in files for cycle in load_discharge_cycles(path)]
    return sorted(cycles, key=lambda cycle: (cycle.measured_on, cycle.cycle_index, cycle.source_file))


def _train_cycles() -> tuple[list[DischargeCycle], int]:
    cycles = load_dataset(CALCE_DIR / "CS2_33")
    pool_size = int(len(cycles) * 0.7)
    pool = cycles[:pool_size]
    if len(pool) > 150:
        indexes = np.linspace(0, len(pool) - 1, 150, dtype=int)
        pool = [pool[int(index)] for index in np.unique(indexes)]
    return pool, pool_size


def _write_figure(cycle: DischargeCycle, fit: FitResult) -> None:
    parameters = asdict(fit)
    prediction, measured = predict_cycle_voltage(
        cycle,
        parameters["r0_ohm"],
        parameters["r1_ohm"],
        parameters["tau_s"],
        np.asarray(parameters["ocv_nodes_v"], dtype=np.float64),
        max_points=500,
    )
    indexes = np.linspace(0, len(cycle.points) - 1, len(measured), dtype=int)
    times_min = np.asarray([cycle.points[int(index)].time_s for index in indexes]) / 60.0
    figure, axis = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
    axis.plot(times_min, measured, color="#111111", linewidth=1.2, label="Measured")
    axis.plot(times_min, prediction, color="#B3261E", linewidth=1.1, label="CS2_33 fit")
    axis.set(
        title="CALCE CS2_34 · cell-held-out discharge cycle",
        xlabel="Elapsed time (min)",
        ylabel="Voltage (V)",
    )
    axis.grid(True, color="#D9D7CF", linewidth=0.6)
    axis.legend(frameon=False, loc="best")
    axis.text(
        0.01,
        0.02,
        f"Cross-cell RMSE {parameters['test_rmse_v']:.4f} V · reference SOC from measured capacity",
        transform=axis.transAxes,
        fontsize=8,
        color="#5B6472",
    )
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE, format="svg")
    plt.close(figure)


def main() -> None:
    training, fit_pool_size = _train_cycles()
    testing = _test_cycles()
    fit = fit_voltage_model(training, testing)
    report = {
        "dataset": "CALCE CS2_33 to CS2_34 cell-held-out voltage-model experiment",
        "sources": {
            "training": "https://web.calce.umd.edu/batteries/data/CS2_33.zip",
            "testing": "https://web.calce.umd.edu/batteries/data/CS2_34.zip",
            "dataset_description": "https://calce.umd.edu/data",
        },
        "archive_sha256": {
            "CS2_33": hashlib.sha256(TRAIN_ARCHIVE.read_bytes()).hexdigest(),
            "CS2_34": hashlib.sha256(TEST_ARCHIVE.read_bytes()).hexdigest(),
        },
        "method": "Fit one-RC voltage model and monotone OCV curve on at most 150 evenly sampled cycles from the first 70% of CS2_33; evaluate every usable CS2_34 cycle, which is a separate physical cell.",
        "protocol": "Both are 1.1 Ah LiCoO2 CS2 cells listed by CALCE as constant-current 0.5C cells; this does not represent an EV pack or vehicle workload.",
        "reference_soc": "Each cycle's logged discharge capacity normalized by its own delivered capacity; reference throughput, not an online SOC estimate.",
        "training_cell": {
            "cell_id": "CS2_33",
            "fitted_cycles": len(training),
            "chronological_fit_pool_cycles": fit_pool_size,
        },
        "held_out_cell": {
            "cell_id": "CS2_34",
            "discharge_cycles": len(testing),
            "first_cycle_date": testing[0].measured_on.isoformat(),
            "last_cycle_date": testing[-1].measured_on.isoformat(),
        },
        "scope_limitations": [
            "Two small lab cells of one chemistry and one nominal cycling rate; not a pack or vehicle.",
            "No temperature time series, cyberattack labels, BMS/CAN traces, or safety-response ground truth.",
            "Measured throughput used to construct reference SOC is unavailable as online ground truth.",
            "No deployment acceptance thresholds were defined; this result is characterization, not qualification.",
        ],
        "fit": asdict(fit),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_figure(testing[-1], fit)
    print(json.dumps(report, indent=2))
    print(f"Wrote {REPORT}")
    print(f"Wrote {FIGURE}")


if __name__ == "__main__":
    main()
