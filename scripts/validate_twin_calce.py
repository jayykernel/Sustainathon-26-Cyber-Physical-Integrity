"""Validate the one-RC voltage model on held-out CALCE CS2_33 cell cycles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from physiguard.eval.calce_validation import (
    DischargeCycle,
    fit_chronological_split,
    load_dataset,
    predict_cycle_voltage,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "raw" / "calce" / "CS2_33"
DEFAULT_ARCHIVE = ROOT / "data" / "raw" / "calce" / "CS2_33.zip"
DEFAULT_REPORT = ROOT / "data" / "results" / "calce_cs2_33_validation.json"
DEFAULT_FIGURE = ROOT / "data" / "results" / "calce_cs2_33_voltage_fit.svg"


def write_figure(cycle: DischargeCycle, report: dict[str, object], output: Path) -> None:
    """Plot measured and fitted voltage for a representative held-out cycle."""
    fit = report["fit"]
    assert isinstance(fit, dict)
    nodes = np.asarray(fit["ocv_nodes_v"], dtype=np.float64)
    prediction, measured = predict_cycle_voltage(
        cycle,
        float(fit["r0_ohm"]),
        float(fit["r1_ohm"]),
        float(fit["tau_s"]),
        nodes,
    )
    selected = np.linspace(0, len(cycle.points) - 1, len(measured), dtype=int)
    points = [cycle.points[int(index)] for index in selected]
    time_min = np.asarray([point.time_s for point in points]) / 60.0

    figure, axis = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
    axis.plot(
        time_min, measured, color="#111111", linewidth=1.25, label="Measured terminal voltage"
    )
    axis.plot(time_min, prediction, color="#FF3366", linewidth=1.1, label="One-RC model fit")
    axis.set(
        title=f"CALCE {'_'.join(cycle.source_file.split('_')[:2])} · held-out discharge cycle",
        xlabel="Elapsed time (min)",
        ylabel="Voltage (V)",
    )
    axis.grid(True, color="#D8D1BD", linewidth=0.6)
    axis.legend(frameon=False, loc="best")
    axis.text(
        0.01,
        0.02,
        f"Test RMSE {float(fit['test_rmse_v']):.4f} V · {fit['test_cycles']} held-out cycles · reference SOC from measured capacity",
        transform=axis.transAxes,
        fontsize=8,
        color="#5D584D",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, format="svg")
    plt.close(figure)


def run(
    data_directory: Path, archive: Path, report_path: Path, figure_path: Path
) -> dict[str, object]:
    """Execute chronological fitting and held-out evaluation on public cell data."""
    cycles = load_dataset(data_directory)
    fit = fit_chronological_split(cycles)
    archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    write_report(report_path, cycles, fit, archive_sha256)
    report = cast(dict[str, object], json.loads(report_path.read_text(encoding="utf-8")))
    testing_count = fit.test_cycles
    split = len(cycles) - testing_count
    write_figure(cycles[-1], report, figure_path)
    print(json.dumps(report, indent=2))
    print(f"Wrote {report_path}")
    print(f"Wrote {figure_path}")
    print(f"Chronological split: {split} training / {testing_count} test cycles")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    args = parser.parse_args()
    run(args.data, args.archive, args.report, args.figure)


if __name__ == "__main__":
    main()
