"""Calibrate and evaluate keyed probe gain, detection, sweep, and overhead."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from physiguard.active_runner import ActiveTrajectory, run_active_scenario
from physiguard.config import CONFIG_DIR, get_config, load_detection_config
from physiguard.detectors.gain import GainDecision, evaluate_gain_window

ROOT = CONFIG_DIR.parent
DEFAULT_OUTPUT = ROOT / "data" / "results" / "probe_report.json"
CALIBRATION_PATH = CONFIG_DIR / "probe_calibration.yaml"
SWEEP_PATH = ROOT / "data" / "results" / "probe_amplitude_sweep.svg"
def _window_gains(
    trajectory: ActiveTrajectory,
    attack_id: str,
    config: Any,
    g_min_v: float | None = None,
    g_min_i: float | None = None,
) -> list[tuple[GainDecision, int]]:
    window = int(config.probe.window)
    results: list[tuple[GainDecision, int]] = []
    starts = range(0, len(trajectory["t"]) - window, int(config.probe.period))
    for start in starts:
        end = start + window
        if end >= len(trajectory["t"]):
            continue
        if attack_id != "baseline" and not np.all(trajectory["attack_active"][start + 1 : end + 1]):
            continue
        delta = trajectory["probe_delta"][start:end]
        if float(delta @ delta) <= 1e-10:
            continue
        voltage = trajectory["V_rep"][start + 1 : end + 1]
        current = trajectory["I_rep"][start + 1 : end + 1]
        current_baseline = trajectory["I_base_cmd"][start:end]
        current_response = current - current_baseline
        initial_soc = float(trajectory["soc_true"][start])
        decision = evaluate_gain_window(
            voltage,
            current_response,
            delta,
            config,
            g_min_v=g_min_v,
            g_min_i=g_min_i,
            initial_soc=initial_soc,
        )
        results.append((decision, start))
    return results


def _calibrate_thresholds(
    gain_pairs: list[tuple[float, float]], config: Any
) -> tuple[float, float, float, float, float]:
    if not gain_pairs:
        raise ValueError("no usable attack-free probe windows were available for calibration")
    challenges_per_hour = 3600.0 / config.probe.period
    target_per_challenge = config.detection.FA_target / challenges_per_hour
    candidate_quantiles = (0.001, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03)
    selected: tuple[float, float, float, float] | None = None
    for q_v in candidate_quantiles:
        for q_i in candidate_quantiles:
            threshold_v = min(
                0.99, float(np.quantile([pair[0] for pair in gain_pairs], q_v))
            )
            threshold_i = min(
                0.99, float(np.quantile([pair[1] for pair in gain_pairs], q_i))
            )
            rate = sum(v < threshold_v or i < threshold_i for v, i in gain_pairs) / len(gain_pairs)
            if rate <= target_per_challenge:
                candidate = (q_v + q_i, min(q_v, q_i), threshold_v, threshold_i)
                if selected is None or candidate[:2] > selected[:2]:
                    selected = candidate
    if selected is None:
        # A short calibration sample may not support any nonzero alarm rate
        # candidate. Choose minima to avoid overstating detections via clean
        # calibration-window alarms.
        q_v = q_i = 0.0
        threshold_v = min(pair[0] for pair in gain_pairs)
        threshold_i = min(pair[1] for pair in gain_pairs)
        selected = (q_v + q_i, min(q_v, q_i), threshold_v, threshold_i)
    _, _, g_min_v, g_min_i = selected
    return (
        min(0.99, g_min_v),
        min(0.99, g_min_i),
        selected[0] / 2.0,
        selected[1],
        target_per_challenge,
    )


def _run_metrics(
    attack_id: str,
    seeds: range,
    amplitude_pct: float,
    config: Any,
    g_min_v: float,
    g_min_i: float,
) -> dict[str, Any]:
    detected = {"V_only": 0, "I_only": 0, "combined": 0, "B2_with_probe": 0}
    voltage_gains: list[float] = []
    current_gains: list[float] = []
    evaluated_windows = 0
    run_count = len(seeds)
    for completed, seed in enumerate(seeds, start=1):
        trace = run_active_scenario(attack_id, seed, amplitude_pct, config)
        windows = _window_gains(trace, attack_id, config, g_min_v, g_min_i)
        if any(item[0].detected_voltage for item in windows):
            detected["V_only"] += 1
        if any(item[0].detected_current for item in windows):
            detected["I_only"] += 1
        if any(item[0].detected_combined for item in windows):
            detected["combined"] += 1
        if attack_id == "baseline":
            if np.any(trace["B2_alarm"]):
                detected["B2_with_probe"] += 1
        elif np.any(trace["B2_alarm"] & trace["attack_active"]):
            detected["B2_with_probe"] += 1
        for result, _ in windows:
            evaluated_windows += 1
            voltage_gains.append(result.voltage.gain)
            current_gains.append(result.current.gain)
        if completed % 10 == 0 or completed == run_count:
            print(f"probe evaluation {attack_id} {amplitude_pct:g}%: {completed}/{run_count}", flush=True)
    return {
        "runs": run_count,
        "evaluated_windows": evaluated_windows,
        "detection_rate": {key: count / run_count for key, count in detected.items()},
        "median_gain": {
            "V": median(voltage_gains) if voltage_gains else None,
            "I": median(current_gains) if current_gains else None,
        },
        "gain_samples": {"V": len(voltage_gains), "I": len(current_gains)},
    }


def _collect_clean_gain_pairs(
    seeds: range, amplitude_pct: float, config: Any
) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for completed, seed in enumerate(seeds, start=1):
        trace = run_active_scenario("baseline", seed, amplitude_pct, config)
        pairs.extend(
            (decision.voltage.gain, decision.current.gain)
            for decision, _ in _window_gains(trace, "baseline", config)
        )
        if completed % 10 == 0 or completed == len(seeds):
            print(
                f"probe sweep calibration {amplitude_pct:g}%: {completed}/{len(seeds)} clean runs",
                flush=True,
            )
    return pairs


def _amplitude_sweep(config: Any, sweep_seed_count: int) -> dict[str, Any]:
    sweep: dict[str, Any] = {
        "amplitudes_pct": config.probe.sweep_amplitudes,
        "calibration_seeds": list(range(sweep_seed_count)),
        "attack_seeds": list(range(sweep_seed_count, 2 * sweep_seed_count)),
        "calibration": {},
        "results": {"AT3": {}, "AT4": {}},
    }
    for amplitude in config.probe.sweep_amplitudes:
        calibration_pairs = _collect_clean_gain_pairs(
            range(sweep_seed_count), float(amplitude), config
        )
        sweep_g_min_v, sweep_g_min_i, q_avg, q_min, target_rate = _calibrate_thresholds(
            calibration_pairs, config
        )
        false_count = sum(
            v < sweep_g_min_v or i < sweep_g_min_i for v, i in calibration_pairs
        )
        sweep["calibration"][f"{amplitude:g}"] = {
            "g_min_V": sweep_g_min_v,
            "g_min_I": sweep_g_min_i,
            "selected_quantile_average": q_avg,
            "minimum_quantile": q_min,
            "target_per_challenge": target_rate,
            "measured_false_alarms_per_hour": (
                false_count / (sweep_seed_count * config.simulation.duration / 3600.0)
            ),
            "clean_windows": len(calibration_pairs),
        }
        for attack_id in ("AT3", "AT4"):
            sweep["results"][attack_id][f"{amplitude:g}"] = _run_metrics(
                attack_id,
                range(sweep_seed_count, 2 * sweep_seed_count),
                float(amplitude),
                config,
                sweep_g_min_v,
                sweep_g_min_i,
            )
    return sweep


def _charge_summary(trajectory: ActiveTrajectory, config: Any) -> dict[str, float | None]:
    soc = trajectory["soc_true"]
    hit = np.flatnonzero(soc >= 0.90)
    charge_time = float(trajectory["t"][hit[0]]) if hit.size else None
    dt_s = float(config.simulation.dt)
    current = trajectory["I_cmd"]
    voltage = trajectory["V_true"]
    input_energy_j = float(np.sum(voltage * current) * dt_s)
    ocv = np.interp(
        np.clip(soc, 0.0, 1.0),
        np.linspace(0.0, 1.0, len(config.twin.OCV_n)),
        np.asarray(config.twin.OCV_n, dtype=np.float64),
    )
    stored_energy_j = float(np.sum(ocv * current) * dt_s * config.plant.eta)
    efficiency = stored_energy_j / input_energy_j if input_energy_j > 0 else None
    return {
        "peak_T_true_c": float(np.max(trajectory["T_true"])),
        "end_T_true_c": float(trajectory["T_true"][-1]),
        "time_to_SOC_0_90_s": charge_time,
        "energy_input_j": input_energy_j,
        "estimated_energy_efficiency": efficiency,
    }


def _overhead_report(
    active_traces: list[ActiveTrajectory],
    config: Any,
) -> dict[str, Any]:
    comparisons: list[dict[str, float | None]] = []
    for seed, active in enumerate(active_traces):
        no_probe = run_active_scenario("baseline", seed, 0.0, config)
        active_summary = _charge_summary(active, config)
        baseline_summary = _charge_summary(no_probe, config)
        active_time = active_summary["time_to_SOC_0_90_s"]
        baseline_time = baseline_summary["time_to_SOC_0_90_s"]
        active_eff = active_summary["estimated_energy_efficiency"]
        baseline_eff = baseline_summary["estimated_energy_efficiency"]
        comparisons.append(
            {
                "delta_peak_T_c": float(active_summary["peak_T_true_c"] - baseline_summary["peak_T_true_c"]),
                "delta_end_T_c": float(active_summary["end_T_true_c"] - baseline_summary["end_T_true_c"]),
                "delta_charge_time_s": (
                    float(active_time - baseline_time)
                    if active_time is not None and baseline_time is not None
                    else None
                ),
                "delta_efficiency_percentage_points": (
                    float((active_eff - baseline_eff) * 100.0)
                    if active_eff is not None and baseline_eff is not None
                    else None
                ),
            }
        )
    fields = comparisons[0].keys() if comparisons else ()
    return {
        "paired_runs": len(comparisons),
        "means": {
            field: float(np.mean([row[field] for row in comparisons if row[field] is not None]))
            if any(row[field] is not None for row in comparisons)
            else None
            for field in fields
        },
        "per_seed": comparisons,
        "efficiency_definition": "eta-weighted nominal OCV energy stored divided by simulated V_true*I_cmd input energy",
    }


def _write_sweep_plot(sweep: dict[str, Any]) -> None:
    amplitudes = [float(value) for value in sweep["amplitudes_pct"]]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for axis, attack in zip(axes, ("AT3", "AT4"), strict=True):
        rows = sweep["results"][attack]
        for key, label in (
            ("B2_with_probe", "B2 with probe present"),
            ("V_only", "Voltage gain test"),
            ("combined", "Combined gain test"),
        ):
            axis.plot(
                amplitudes,
                [rows[f"{value:g}"]["detection_rate"][key] for value in amplitudes],
                marker="o",
                label=label,
            )
        axis.set_title(f"{attack} detection")
        axis.set_xlabel("Probe amplitude (% of I_req)")
        axis.set_ylim(-0.03, 1.03)
        axis.grid(True, alpha=0.25)
    axes[0].set_ylabel("Detection rate")
    axes[1].legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(SWEEP_PATH, format="svg")
    plt.close(fig)
    svg_lines = SWEEP_PATH.read_text(encoding="utf-8").splitlines()
    SWEEP_PATH.write_text(
        "\n".join(line.rstrip() for line in svg_lines) + "\n", encoding="utf-8"
    )


def make_report(seed_count: int = 100, sweep_seed_count: int = 20) -> dict[str, Any]:
    """Calibrate on clean validation runs, then evaluate attacks, sweep, and overhead."""
    if seed_count < 2 or sweep_seed_count < 1:
        raise ValueError("seed_count must be at least two and sweep_seed_count must be positive")
    config = get_config()
    load_detection_config(base_config=config)
    baseline_gains_v: list[float] = []
    baseline_gains_i: list[float] = []
    baseline_window_gains: list[tuple[float, float]] = []
    overhead_traces: list[ActiveTrajectory] = []
    for completed, seed in enumerate(range(seed_count), start=1):
        trace = run_active_scenario("baseline", seed, config.probe.amplitude_pct, config)
        windows = _window_gains(trace, "baseline", config)
        for result, _ in windows:
            baseline_gains_v.append(result.voltage.gain)
            baseline_gains_i.append(result.current.gain)
            baseline_window_gains.append((result.voltage.gain, result.current.gain))
        if seed < min(20, seed_count):
            overhead_traces.append(trace)
        if completed % 10 == 0 or completed == seed_count:
            print(f"probe calibration: {completed}/{seed_count} clean runs", flush=True)

    g_min_v, g_min_i, selected_quantile, minimum_quantile, target_per_challenge = (
        _calibrate_thresholds(baseline_window_gains, config)
    )
    baseline_detected_v = sum(value < g_min_v for value in baseline_gains_v)
    baseline_detected_i = sum(value < g_min_i for value in baseline_gains_i)
    baseline_detected_combined = sum(
        v < g_min_v or i < g_min_i for v, i in baseline_window_gains
    )
    baseline_exposure_hours = seed_count * config.simulation.duration / 3600.0
    calibration = {
        "source": "attack-free validation windows",
        "seeds": list(range(seed_count)),
        "gain_windows": len(baseline_window_gains),
        "target_combined_FA_per_hour": config.detection.FA_target,
        "selected_channel_quantile_average": selected_quantile,
        "minimum_channel_quantile": minimum_quantile,
        "target_combined_FA_per_challenge": target_per_challenge,
        "g_min_V": g_min_v,
        "g_min_I": g_min_i,
        "measured_false_alarms": {
            "V_only_per_hour": baseline_detected_v / baseline_exposure_hours,
            "I_only_per_hour": baseline_detected_i / baseline_exposure_hours,
            "combined_per_hour": baseline_detected_combined / baseline_exposure_hours,
            "combined_per_challenge": baseline_detected_combined / max(1, len(baseline_window_gains)),
        },
        "combined_FA_budget_met": (
            baseline_detected_combined / baseline_exposure_hours <= config.detection.FA_target
        ),
        "config_hash": config.config_hash(),
    }
    CALIBRATION_PATH.write_text(yaml.safe_dump(calibration, sort_keys=False), encoding="utf-8")

    attack_results: dict[str, Any] = {}
    attack_seed_range = range(seed_count)
    for attack_id in ("AT3", "AT4", "AT6"):
        attack_results[attack_id] = _run_metrics(
            attack_id,
            attack_seed_range,
            config.probe.amplitude_pct,
            config,
            g_min_v,
            g_min_i,
        )

    sweep = _amplitude_sweep(config, sweep_seed_count)
    _write_sweep_plot(sweep)

    overhead = _overhead_report(overhead_traces, config)
    report = {
        "split": "validation",
        "config_hash": config.config_hash(),
        "probe": {
            "amplitude_pct": config.probe.amplitude_pct,
            "chip_length_s": config.probe.chip_length,
            "window_s": config.probe.window,
            "period_s": config.probe.period,
            "keyed_prng": "HMAC-SHA256(key, nonce) -> PCG64",
            "balanced_chips": True,
            "safety_bounds": ["0 <= I_cmd <= I_rated", "one-step V <= V_max", "one-step T <= T_warn"],
        },
        "calibration": calibration,
        "attacks": attack_results,
        "amplitude_sweep": sweep,
        "overhead": overhead,
        "oracle_note": "AT6 receives true actuator current including the probe and is the explicit A2 limit case.",
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--sweep-seeds", type=int, default=20)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sweep-only", action="store_true")
    args = parser.parse_args()
    if args.sweep_only:
        if not args.output.exists():
            parser.error("--sweep-only requires an existing probe report at --output")
        report = json.loads(args.output.read_text(encoding="utf-8"))
        report["amplitude_sweep"] = _amplitude_sweep(get_config(), args.sweep_seeds)
        _write_sweep_plot(report["amplitude_sweep"])
        args.output.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        print(f"updated amplitude sweep and wrote {args.output}")
        return
    report = make_report(args.seeds, args.sweep_seeds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"gain thresholds: {report['calibration']}")
    for attack, metrics in report["attacks"].items():
        print(f"{attack} active results: {metrics['detection_rate']}; median gain {metrics['median_gain']}")
    print(f"probe amplitude figure: {SWEEP_PATH}")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
