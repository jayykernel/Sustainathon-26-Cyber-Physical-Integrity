"""Known-sequence tests for P2 passive detector primitives."""

import numpy as np
import pytest

from physiguard.config import Config
from physiguard.detectors.cusum import CUSUM
from physiguard.detectors.nis import NISWindow
from physiguard.detectors.passive import PassiveDetectors
from physiguard.detectors.range_check import RangeCheck
from physiguard.eval.passive import PassiveTrace, calibrate_thresholds


def test_nis_window_sums_a_complete_window_and_alarms_at_known_sample() -> None:
    detector = NISWindow(window_size=3, threshold=5.0)

    assert detector.update(1.0).alarm is False
    assert detector.update(1.0).statistic is None
    result = detector.update(4.0)
    assert result.statistic == pytest.approx(6.0)
    assert result.alarm is True
    assert detector.update(0.0).statistic == pytest.approx(5.0)
    assert detector.update(0.0).alarm is False


def test_cusum_has_known_positive_negative_alarm_times_and_resets() -> None:
    positive = CUSUM(kappa=0.5, threshold=1.5)
    assert positive.update(2.0).alarm is False
    assert positive.update(2.0).alarm is True
    assert positive.positive == 0.0
    assert positive.update(-2.0).alarm is False
    assert positive.update(-2.0).alarm is True


def test_range_check_flags_static_bounds_and_five_second_temperature_slew() -> None:
    detector = RangeCheck(Config())
    for _ in range(5):
        flags = detector.check(3.7, 50.0, 35.0)
    assert flags == set()
    assert "dTdt" in detector.check(3.7, 50.0, 39.0)
    assert "V" in detector.check(4.31, 50.0, 35.0)
    assert "I" in detector.check(3.7, 190.0, 35.0)
    assert "T" in detector.check(3.7, 50.0, 56.0)


def test_passive_monitor_combines_channels_and_standardizes_residuals() -> None:
    config = Config()
    config.detection.NIS_window = 1
    config.detection.NIS_threshold = 1.0
    config.detection.CUSUM_h = 100.0
    monitor = PassiveDetectors(config)

    result = monitor.update(
        nis=2.0,
        innovation=np.array([0.02, -0.2]),
        innovation_std=np.array([0.01, 0.1]),
        current_residual=0.1,
        voltage_v=3.7,
        current_a=50.0,
        temperature_c=35.0,
    )

    assert "NIS" in result["alarms"]
    assert result["z"] == {"V": 2.0, "T": -2.0, "I": 0.5}
    assert result["nis_window_sum"] == pytest.approx(2.0)


def test_calibration_rejects_held_out_test_seeds() -> None:
    config = Config()
    zeros = np.zeros(60, dtype=np.float64)
    test_trace = PassiveTrace(
        seed=100,
        nis=zeros,
        z_v=zeros,
        z_t=zeros,
        z_i=zeros,
        range_alarm=zeros.astype(np.bool_),
    )

    with pytest.raises(ValueError, match="outside the configured validation split"):
        calibrate_thresholds([test_trace], config)
