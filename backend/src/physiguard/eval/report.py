"""Validate and export evaluation JSON, CSV, Markdown, metadata, and figures."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..config import CONFIG_DIR
from .schema import EvaluationMetadataModel, EvaluationReportModel

ROOT = CONFIG_DIR.parent
RESULTS_DIR = ROOT / "data" / "results"
DETECTOR_ORDER = ("B0", "B1", "B2", "B2_probe_present", "B3")


def write_report(
    data: dict[str, Any],
    *,
    results_dir: Path = RESULTS_DIR,
    metadata: dict[str, Any],
) -> None:
    """Validate and write the stable report outputs and required SVG figures."""
    report = EvaluationReportModel.model_validate(
        {key: value for key, value in data.items() if key != "details"}
    )
    meta = EvaluationMetadataModel.model_validate(metadata)
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "results.json").write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (results_dir / "meta.json").write_text(
        json.dumps(meta.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(report.model_dump(mode="json"), results_dir / "results.csv")
    _write_tables(report.model_dump(mode="json"), results_dir / "tables.md")
    _write_figures(report.model_dump(mode="json"), data, results_dir)


def _write_csv(report: dict[str, Any], path: Path) -> None:
    columns = (
        "scenario",
        "detector",
        "runs",
        "detections",
        "attack_activated_runs",
        "preempted_before_activation_runs",
        "detection_rate",
        "detection_ci_low",
        "detection_ci_high",
        "median_delay_s",
        "delay_iqr_low_s",
        "delay_iqr_high_s",
        "median_safety_margin",
        "safety_margin_unit",
        "false_alarm_episodes",
        "false_alarm_hours",
        "false_alarms_per_hour",
        "fa_ci_low",
        "fa_ci_high",
        "mean_peak_temperature_c",
        "mean_peak_voltage_v",
        "hazard_events",
        "hazard_event_rate",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for scenario, detectors in report["scenarios"].items():
            for detector in DETECTOR_ORDER:
                metric = detectors[detector]
                detection_ci = metric["detection_ci_95"] or (None, None)
                delay_iqr = metric["delay_iqr_s"] or (None, None)
                fa_ci = metric["false_alarm_rate_ci_95"]
                writer.writerow(
                    {
                        "scenario": scenario,
                        "detector": detector,
                        "runs": metric["runs"],
                        "detections": metric["detections"],
                        "attack_activated_runs": metric["attack_activated_runs"],
                        "preempted_before_activation_runs": metric[
                            "preempted_before_activation_runs"
                        ],
                        "detection_rate": metric["detection_rate"],
                        "detection_ci_low": detection_ci[0],
                        "detection_ci_high": detection_ci[1],
                        "median_delay_s": metric["median_delay_s"],
                        "delay_iqr_low_s": delay_iqr[0],
                        "delay_iqr_high_s": delay_iqr[1],
                        "median_safety_margin": metric["median_safety_margin"],
                        "safety_margin_unit": metric["safety_margin_unit"],
                        "false_alarm_episodes": metric["false_alarm_episodes"],
                        "false_alarm_hours": metric["false_alarm_hours"],
                        "false_alarms_per_hour": metric["false_alarms_per_hour"],
                        "fa_ci_low": fa_ci[0],
                        "fa_ci_high": fa_ci[1],
                        "mean_peak_temperature_c": metric["mean_peak_temperature_c"],
                        "mean_peak_voltage_v": metric["mean_peak_voltage_v"],
                        "hazard_events": metric["hazard_events"],
                        "hazard_event_rate": metric["hazard_event_rate"],
                    }
                )


def _rate_text(metric: dict[str, Any]) -> str:
    if metric["detection_rate"] is None:
        return "—"
    low, high = metric["detection_ci_95"]
    return f"{metric['detection_rate']:.1%} ({low:.1%}–{high:.1%})"


def _write_tables(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Evaluation results",
        "",
        f"Test seeds: {report['seeds'][0]}–{report['seeds'][-1]}; duration: {report['duration_s']} s.",
        "",
        "Detection rate includes Wilson 95% confidence intervals and uses runs where the attack activated; B3 preemptions are reported separately below. False alarms are merged into episodes when alarms occur within 60 seconds.",
        "",
        "| Scenario | B0 | B1 | B2 | B2 + probe present | B3 full |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario, detectors in report["scenarios"].items():
        lines.append(
            "| "
            + scenario
            + " | "
            + " | ".join(_rate_text(detectors[name]) for name in DETECTOR_ORDER)
            + " |"
        )
    lines.extend(
        [
            "",
            "## Safety and alarm burden",
            "",
            "| Scenario | Detector | FA episodes/hour | Median delay (s) | Peak T (°C) | Peak V (V) | Hazard rate |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for scenario, detectors in report["scenarios"].items():
        for detector in DETECTOR_ORDER:
            metric = detectors[detector]
            delay = "—" if metric["median_delay_s"] is None else f"{metric['median_delay_s']:.1f}"
            lines.append(
                f"| {scenario} | {detector} | {metric['false_alarms_per_hour']:.3f} "
                f"| {delay} | {metric['mean_peak_temperature_c']:.2f} "
                f"| {metric['mean_peak_voltage_v']:.4f} | {metric['hazard_event_rate']:.1%} |"
            )
    lines.extend(
        [
            "",
            "## Paired B3 safety change",
            "",
            "| Scenario | Δ peak T reduction (°C) | Δ peak V reduction (V) | Hazard rate reduction | Preempted before activation |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for scenario, detectors in report["scenarios"].items():
        paired = detectors["paired_safety"]
        lines.append(
            f"| {scenario} | {paired['mean_peak_temperature_reduction_c']:.3f} "
            f"| {paired['mean_peak_voltage_reduction_v']:.4f} "
            f"| {paired['hazard_rate_reduction']:.1%} "
            f"| {paired['preempted_before_activation_runs']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _save_svg(fig: Any, path: Path) -> None:
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def _write_figures(report: dict[str, Any], data: dict[str, Any], results_dir: Path) -> None:
    attacks = [name for name in report["scenarios"] if name != "baseline"]
    fig, axis = plt.subplots(figsize=(10, 5))
    x = np.arange(len(attacks))
    width = 0.15
    for offset, detector in enumerate(DETECTOR_ORDER):
        values = [report["scenarios"][attack][detector]["detection_rate"] or 0.0 for attack in attacks]
        axis.bar(x + (offset - 2) * width, values, width, label=detector)
    axis.set_xticks(x, attacks)
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("Detection rate")
    axis.set_title("Detector ladder on held-out test seeds")
    axis.legend(ncols=3)
    axis.grid(axis="y", alpha=0.25)
    _save_svg(fig, results_dir / "detector_ladder.svg")

    details = data.get("details", {})
    fig, axis = plt.subplots(figsize=(10, 5))
    delay_series: list[list[float]] = []
    labels: list[str] = []
    for attack in attacks:
        for detector in ("B2", "B2_probe_present", "B3"):
            values = [
                float(row["detectors"][detector]["delay_s"])
                for row in details.get(attack, [])
                if row["detectors"][detector]["delay_s"] is not None
            ]
            if values:
                delay_series.append(values)
                labels.append(f"{attack}\n{detector}")
    if delay_series:
        axis.boxplot(delay_series, tick_labels=labels, showfliers=False)
    axis.set_ylabel("Detection delay (s)")
    axis.set_title("Detection delay distributions")
    axis.tick_params(axis="x", labelsize=7)
    axis.grid(axis="y", alpha=0.25)
    _save_svg(fig, results_dir / "delay_distributions.svg")

    sweep_path = RESULTS_DIR / "probe_report.json"
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))["amplitude_sweep"]
    fig, axis = plt.subplots(figsize=(7, 4))
    amplitudes = sweep["amplitudes_pct"]
    for detector, style in (("combined", "o-"), ("V_only", "s--")):
        rates = [
            sweep["results"]["AT3"][f"{float(amplitude):g}"]["detection_rate"][detector]
            for amplitude in amplitudes
        ]
        axis.plot(amplitudes, rates, style, label=f"AT3 {detector}")
        rates_at4 = [
            sweep["results"]["AT4"][f"{float(amplitude):g}"]["detection_rate"][detector]
            for amplitude in amplitudes
        ]
        axis.plot(amplitudes, rates_at4, style, label=f"AT4 {detector}", alpha=0.7)
    axis.set_xlabel("Probe amplitude (% of I_req)")
    axis.set_ylabel("Detection rate")
    axis.set_ylim(-0.03, 1.03)
    axis.set_title("Validation probe-amplitude sweep")
    axis.legend(fontsize=8, ncols=2)
    axis.grid(alpha=0.25)
    _save_svg(fig, results_dir / "detection_vs_probe_amplitude.svg")

    matrices = list(report["localization_confusion"].values())
    counts = np.sum(np.asarray([matrix["counts"] for matrix in matrices]), axis=0)
    labels = matrices[0]["labels"]
    fig, axis = plt.subplots(figsize=(7, 6))
    image = axis.imshow(counts, cmap="Blues")
    axis.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    axis.set_yticks(range(len(labels)), labels)
    axis.set_xlabel("Predicted channel")
    axis.set_ylabel("Injected fault channel")
    axis.set_title("B3 localization confusion matrix")
    fig.colorbar(image, ax=axis, label="Samples")
    _save_svg(fig, results_dir / "localization_confusion.svg")

    overhead = json.loads(sweep_path.read_text(encoding="utf-8"))["overhead"]["means"]
    fields = (
        ("delta_peak_T_c", "Peak T Δ (°C)"),
        ("delta_charge_time_s", "Charge time Δ (s)"),
        ("delta_efficiency_percentage_points", "Efficiency Δ (pp)"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(8, 3))
    for axis, (field, title) in zip(axes, fields, strict=True):
        axis.bar((title,), (float(overhead.get(field, 0.0) or 0.0),))
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_title(title, fontsize=9)
        axis.tick_params(axis="x", labelsize=7)
        axis.grid(axis="y", alpha=0.25)
    fig.suptitle("P5 measured probe overhead (validation, 20 pairs)")
    _save_svg(fig, results_dir / "probe_overhead.svg")
