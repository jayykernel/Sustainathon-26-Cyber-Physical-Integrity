"""Calibrate passive detector thresholds from validation seeds 0 through 99."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import chi2  # type: ignore[import-untyped]

from ..config import CONFIG_DIR, Config, load_config
from .passive import PassiveTrace, calibrate_thresholds, generate_passive_trace

ROOT = CONFIG_DIR.parent
VALIDATION_SEEDS = list(range(100))


def _write_json(path: Path, data: object) -> None:
    """Write one UTF-8 JSON artifact with parent directories created."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _nis_qq_data(traces: list[PassiveTrace], config_hash: str) -> dict[str, object]:
    """Build chi-square diagnostic quantiles without claiming a calibrated fit."""
    values = np.concatenate([trace.nis for trace in traces])
    probabilities = np.linspace(0.01, 0.99, 99)
    return {
        "source": "attack-free validation seeds only",
        "seeds": VALIDATION_SEEDS,
        "config_hash": config_hash,
        "sample_count": int(values.size),
        "degrees_of_freedom": 2,
        "probability": probabilities.tolist(),
        "theoretical_chi_square": chi2.ppf(probabilities, df=2).tolist(),
        "observed_nis": np.quantile(values, probabilities).tolist(),
    }


def calibrate(config: Config | None = None) -> tuple[Path, dict[str, object]]:
    """Run validation-only calibration and write thresholds plus diagnostics."""
    base = config or load_config()
    config_hash = base.config_hash()
    traces: list[PassiveTrace] = []
    for seed in VALIDATION_SEEDS:
        traces.append(generate_passive_trace(base, seed, base.simulation.duration))
        if (seed + 1) % 10 == 0:
            print(f"calibration: generated {seed + 1}/100 validation runs")

    detection, metrics = calibrate_thresholds(traces, base)
    detection.calibration_seeds = VALIDATION_SEEDS
    detection.calibration_config_hash = config_hash
    detection.calibration_date = datetime.now(UTC).date().isoformat()
    detection_path = CONFIG_DIR / "detection.yaml"
    detection_path.write_text(
        yaml.safe_dump(detection.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )

    validation_report: dict[str, object] = {
        "split": "validation",
        "seeds": VALIDATION_SEEDS,
        "config_hash": config_hash,
        "calibration_date": detection.calibration_date,
        "NIS_threshold": detection.NIS_threshold,
        "NIS_window": detection.NIS_window,
        "CUSUM_h": detection.CUSUM_h,
        "FA_target_per_hour": detection.FA_target,
        "validation_hours": metrics["exposure_hours"],
        **metrics,
    }
    _write_json(ROOT / "data" / "results" / "passive_fa_validation.json", validation_report)
    _write_json(ROOT / "data" / "results" / "nis_qq.json", _nis_qq_data(traces, config_hash))

    print(f"wrote {detection_path}")
    print(
        "validation combined false alarms: "
        f"{metrics['combined_events']} events / {metrics['exposure_hours']:.2f} h "
        f"= {metrics['combined_fa_per_hour']:.4f}/h "
        f"(target {detection.FA_target:.3f}/h)"
    )
    print(f"NIS window-sum threshold: {detection.NIS_threshold:.6g}")
    print(f"CUSUM threshold: {detection.CUSUM_h:.6g}")
    return detection_path, validation_report


if __name__ == "__main__":
    calibrate()
