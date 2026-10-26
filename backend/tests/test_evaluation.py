"""P7 metric and reduced-run reproducibility checks."""

import json

from physiguard.config import get_config
from physiguard.eval.metrics import (
    alarm_episode_times,
    first_detection_episode,
    summarize_detection_runs,
    wilson_interval,
)
from physiguard.eval.runner import run_evaluation


def test_wilson_interval_and_alarm_episode_merging() -> None:
    low, high = wilson_interval(5, 10)
    assert 0.23 < low < 0.24
    assert 0.76 < high < 0.77
    assert alarm_episode_times(
        [False, True, False, True, False, True],
        [0, 1, 2, 30, 31, 100],
        merge_gap_s=60.0,
    ) == [1.0, 100.0]
    assert first_detection_episode([1.0], 50.0) is None
    assert first_detection_episode([1.0, 100.0], 50.0) == 100.0


def test_preempted_runs_are_separate_from_detector_detection_rate() -> None:
    result = summarize_detection_runs(
        [
            {
                "detected": True,
                "attack_activated": True,
                "preempted_before_activation": False,
                "delay_s": 2.0,
                "safety_margin": 1.0,
                "false_alarm_episodes": 0,
                "false_alarm_hours": 0.1,
                "peak_temperature_c": 45.0,
                "peak_voltage_v": 4.1,
                "hazard_event": False,
                "hazard_samples": 0,
            },
            {
                "detected": False,
                "attack_activated": False,
                "preempted_before_activation": True,
                "delay_s": None,
                "safety_margin": None,
                "false_alarm_episodes": 1,
                "false_alarm_hours": 0.2,
                "peak_temperature_c": 44.0,
                "peak_voltage_v": 4.0,
                "hazard_event": False,
                "hazard_samples": 0,
            },
        ],
        attacked=True,
        duration_hours=0.3,
        safety_unit="°C",
    )
    assert result["runs"] == 2
    assert result["detections"] == 1
    assert result["attack_activated_runs"] == 1
    assert result["preempted_before_activation_runs"] == 1
    assert result["detection_rate"] == 1.0


def test_held_out_evaluation_seeds_do_not_overlap_calibration() -> None:
    held_out = set(range(1000, 1200))
    calibration = set(get_config().detection.calibration_seeds)
    assert held_out.isdisjoint(calibration)


def test_reduced_evaluation_is_bit_for_bit_repeatable() -> None:
    first = run_evaluation(
        start_seed=1000,
        run_count=1,
        duration_s=3600,
        workers=7,
        progress=False,
    )
    second = run_evaluation(
        start_seed=1000,
        run_count=1,
        duration_s=3600,
        workers=7,
        progress=False,
    )
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(
        second, sort_keys=True, allow_nan=False
    )
