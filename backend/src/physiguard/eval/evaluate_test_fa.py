"""Measure attack-free false alarms once on held-out test seeds 100–199."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ..config import CONFIG_DIR, load_config, load_detection_config
from .passive import PassiveTrace, generate_passive_trace, summarize_false_alarms

ROOT = CONFIG_DIR.parent
TEST_SEEDS = list(range(100, 200))
OUTPUT_PATH = ROOT / "data" / "results" / "passive_fa_test.json"


def evaluate_test_fa() -> dict[str, object]:
    """Run the frozen calibration thresholds once on seeds excluded from fitting."""
    if OUTPUT_PATH.exists():
        raise FileExistsError(
            f"Test false-alarm report already exists: {OUTPUT_PATH}; refusing to overwrite"
        )
    base = load_config()
    detection = load_detection_config(base_config=base)
    if not detection.calibration_config_hash:
        raise ValueError("detection.yaml has no calibration metadata; run make calibrate first")
    overlap = set(TEST_SEEDS).intersection(detection.calibration_seeds)
    if overlap:
        raise ValueError(f"test seeds overlap calibration seeds: {sorted(overlap)}")

    traces: list[PassiveTrace] = []
    for seed in TEST_SEEDS:
        traces.append(generate_passive_trace(base, seed, base.simulation.duration))
        if (seed + 1) % 10 == 0:
            print(f"test evaluation: generated {seed - TEST_SEEDS[0] + 1}/100 runs")

    metrics = summarize_false_alarms(traces, base, detection)
    report: dict[str, object] = {
        "split": "test",
        "seeds": TEST_SEEDS,
        "calibration_seeds": detection.calibration_seeds,
        "calibration_config_hash": detection.calibration_config_hash,
        "evaluated_config_hash": base.config_hash(),
        "evaluation_date": datetime.now(UTC).date().isoformat(),
        "thresholds_frozen_from_validation": {
            "NIS_threshold": detection.NIS_threshold,
            "NIS_window": detection.NIS_window,
            "CUSUM_h": detection.CUSUM_h,
        },
        "FA_target_per_hour": detection.FA_target,
        **metrics,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        f"test combined false alarms: {metrics['combined_events']} events / "
        f"{metrics['exposure_hours']:.2f} h = "
        f"{metrics['combined_fa_per_hour']:.4f}/h "
        f"(target {detection.FA_target:.3f}/h); thresholds unchanged"
    )
    return report


if __name__ == "__main__":
    evaluate_test_fa()
