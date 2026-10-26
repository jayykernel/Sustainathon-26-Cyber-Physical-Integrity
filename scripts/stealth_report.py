"""Measure passive B0/B1/B2 detection across deterministic validation attacks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any, Literal, cast

import numpy as np

from physiguard.attacks.runner import run_attack_scenario
from physiguard.config import CONFIG_DIR, get_config, load_detection_config

ROOT = CONFIG_DIR.parent
DEFAULT_OUTPUT = ROOT / "data" / "results" / "stealth_report.json"
ATTACKS = ("AT1", "AT2", "AT3", "AT4", "AT5", "AT6")
DETECTORS = ("B0_alarm", "B1_alarm", "B2_alarm")


def make_report(seeds: range, duration_s: int | None = None) -> dict[str, Any]:
    """Run every attack and report per-run detection rates and delays."""
    config = get_config()
    detection = load_detection_config(base_config=config)
    rows: dict[str, dict[str, list[bool]]] = {
        attack: {detector: [] for detector in DETECTORS} for attack in ATTACKS
    }
    delays: dict[str, dict[str, list[float]]] = {
        attack: {detector: [] for detector in DETECTORS} for attack in ATTACKS
    }
    completed = 0
    total = len(seeds) * len(ATTACKS)
    for seed in seeds:
        for attack in ATTACKS:
            trace = run_attack_scenario(attack, seed, config, duration_s)
            active = trace["attack_active"]
            active_indices = np.flatnonzero(active)
            for detector in DETECTORS:
                alarms = trace[
                    cast(Literal["B0_alarm", "B1_alarm", "B2_alarm"], detector)
                ]
                alarm_indices = np.flatnonzero(alarms & active)
                rows[attack][detector].append(bool(alarm_indices.size))
                if alarm_indices.size and active_indices.size:
                    delays[attack][detector].append(
                        float(trace["t"][alarm_indices[0]] - trace["t"][active_indices[0]])
                    )
            completed += 1
            if completed % 20 == 0 or completed == total:
                print(f"stealth report: {completed}/{total} simulations", flush=True)

    results: dict[str, Any] = {}
    for attack in ATTACKS:
        results[attack] = {}
        for detector in DETECTORS:
            detected = rows[attack][detector]
            delay_values = delays[attack][detector]
            results[attack][detector.removesuffix("_alarm")] = {
                "detections": sum(detected),
                "runs": len(detected),
                "rate": sum(detected) / len(detected),
                "median_delay_s": median(delay_values) if delay_values else None,
            }
    return {
        "split": "validation",
        "seeds": list(seeds),
        "duration_s": duration_s or config.simulation.duration,
        "config_hash": config.config_hash(),
        "calibration_config_hash": detection.calibration_config_hash,
        "thresholds": {
            "NIS_threshold": detection.NIS_threshold,
            "NIS_window": detection.NIS_window,
            "CUSUM_h": detection.CUSUM_h,
            "CUSUM_kappa": detection.CUSUM_kappa,
        },
        "detection": results,
        "gate": {
            "AT4_B2_not_over_90_percent": results["AT4"]["B2"]["rate"] <= 0.90,
            "AT2_B1_missed_more_often_than_B2": results["AT2"]["B1"]["rate"]
            < results["AT2"]["B2"]["rate"],
            "AT1_B2_detected": results["AT1"]["B2"]["rate"] > 0.0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=100, help="number of validation seeds from zero")
    parser.add_argument("--duration", type=int, default=None, help="simulation length in seconds")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    report = make_report(range(args.seeds), args.duration)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for attack, detectors in report["detection"].items():
        rates = ", ".join(f"{name}={values['rate']:.3f}" for name, values in detectors.items())
        print(f"{attack}: {rates}")
    print(f"stealth gates: {report['gate']}")
    print(f"wrote {args.output}")
    if not all(report["gate"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
