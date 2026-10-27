"""Recalibrate P5 gain thresholds on the fixed clean validation seed split."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import yaml
from probe_report import CALIBRATION_PATH, _calibrate_thresholds, _window_gains

from physiguard.active_runner import run_active_scenario
from physiguard.config import get_config, load_detection_config
from physiguard.detectors.gain import GAIN_CONFIDENCE_Z

ROOT = Path(__file__).resolve().parents[1]
SEEDS = list(range(100))
REPORT_PATH = ROOT / "data" / "results" / "probe_calibration_validation.json"


def main() -> None:
    config = get_config()
    detection = load_detection_config(base_config=config)
    continuous_config = deepcopy(config)
    continuous_config.probe.period = continuous_config.probe.window
    gain_pairs: list[tuple[float, float]] = []
    for completed, seed in enumerate(SEEDS, start=1):
        trace = run_active_scenario(
            "baseline",
            seed,
            continuous_config.probe.amplitude_pct,
            continuous_config,
            detection_override=detection,
        )
        gain_pairs.extend(
            (
                decision.voltage.gain + GAIN_CONFIDENCE_Z * decision.voltage.standard_error,
                decision.current.gain + GAIN_CONFIDENCE_Z * decision.current.standard_error,
            )
            for decision, _ in _window_gains(
                trace,
                "baseline",
                continuous_config,
                g_min_v=continuous_config.probe.g_min_V,
                g_min_i=continuous_config.probe.g_min_I,
            )
        )
        if completed % 10 == 0:
            print(f"probe validation calibration: {completed}/{len(SEEDS)} clean runs", flush=True)

    g_min_v, g_min_i, q_average, q_minimum, target_per_challenge = _calibrate_thresholds(
        gain_pairs, continuous_config
    )
    exposure_hours = len(SEEDS) * continuous_config.simulation.duration / 3600.0
    false_alarm_windows = sum(v < g_min_v or i < g_min_i for v, i in gain_pairs)
    calibration = {
        "source": "attack-free validation windows",
        "probe_schedule": "continuous 120-second challenge windows (period equals challenge window); conservative calibration for SUSPECT/CONFIRMED/SAFE_MODE operation",
        "gain_statistic": f"gain + {GAIN_CONFIDENCE_Z:.2f} × standard error (95% two-sided confidence upper bound)",
        "seeds": SEEDS,
        "gain_windows": len(gain_pairs),
        "target_combined_FA_per_hour": config.detection.FA_target,
        "selected_channel_quantile_average": q_average,
        "minimum_channel_quantile": q_minimum,
        "target_combined_FA_per_challenge": target_per_challenge,
        "g_min_V": g_min_v,
        "g_min_I": g_min_i,
        "measured_false_alarms": {
            "combined_false_alarm_windows": false_alarm_windows,
            "combined_per_hour": false_alarm_windows / exposure_hours,
        },
        "combined_FA_budget_met": false_alarm_windows / exposure_hours
        <= config.detection.FA_target,
        "config_hash": config.config_hash(),
        "calibration_schedule_period_s": continuous_config.probe.period,
    }
    CALIBRATION_PATH.write_text(yaml.safe_dump(calibration, sort_keys=False), encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(calibration, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {CALIBRATION_PATH}")
    print(f"wrote {REPORT_PATH}")
    print(
        f"validation combined false alarms: {false_alarm_windows}/{len(gain_pairs)} windows; "
        f"{calibration['measured_false_alarms']['combined_per_hour']:.4f}/h "
        f"(target {config.detection.FA_target:.3f}/h)"
    )


if __name__ == "__main__":
    main()
