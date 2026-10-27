"""Localization scoring, cross-prediction, and confusion-matrix tests."""

import math

import numpy as np
import pytest

from physiguard.config import get_config
from physiguard.eval.metrics import confusion_matrix
from physiguard.localize import (
    LocalizationConfig,
    LocalizationEngine,
    classify_scores,
    load_localization_config,
)
from physiguard.twin import EKF


def test_synthetic_single_channel_faults_localize_voltage_and_temperature() -> None:
    settings = LocalizationConfig(score_threshold=2.0, dominance_ratio=1.5)

    voltage = classify_scores({"V": 7.0, "T": 0.5, "I": 0.3}, True, settings)
    temperature = classify_scores({"V": 0.5, "T": 7.0, "I": 0.3}, True, settings)

    assert voltage["channel"] == "v"
    assert temperature["channel"] == "temp"
    assert voltage["confidence"] > 0.0
    assert temperature["confidence"] > 0.0


@pytest.mark.parametrize(
    ("fault_channel", "expected_channel"),
    [("V_rep", "v"), ("T_rep", "temp")],
)
def test_ekf_bank_localizes_a_synthetic_single_channel_step(
    fault_channel: str, expected_channel: str
) -> None:
    engine = LocalizationEngine(
        get_config(), LocalizationConfig(window_s=10.0, score_threshold=2.0)
    )
    result = None
    for index in range(15):
        voltage = 3.9 if fault_channel == "V_rep" and index >= 10 else 3.7
        temperature = 40.0 if fault_channel == "T_rep" and index >= 10 else 35.0
        result = engine.update(voltage, 0.0, temperature, 0.0, alarm=True)

    assert result is not None
    assert result["channel"] == expected_channel


def test_localization_rolling_rms_matches_full_window_reference() -> None:
    engine = LocalizationEngine(get_config(), LocalizationConfig(window_s=7.0, score_threshold=2.0))
    rng = np.random.default_rng(4907)
    for _ in range(40):
        voltage = 3.7 + float(rng.normal(0.0, 0.02))
        current = 10.0 + float(rng.normal(0.0, 0.1))
        temperature = 35.0 + float(rng.normal(0.0, 0.2))
        result = engine.update(voltage, current, temperature, current, alarm=True)
        if engine.residuals["V_cross"]:
            assert result["evidence"]["V"] == pytest.approx(
                engine._rms(engine.residuals["V"], engine.residuals["V_cross"]),
                rel=1e-12,
                abs=1e-12,
            )
            assert result["evidence"]["T"] == pytest.approx(
                engine._rms(engine.residuals["T"], engine.residuals["T_cross"]),
                rel=1e-12,
                abs=1e-12,
            )
            assert result["evidence"]["I"] == pytest.approx(
                engine._rms(engine.residuals["I"]), rel=1e-12, abs=1e-12
            )


def test_localization_labels_multi_command_unknown_and_none() -> None:
    settings = LocalizationConfig(score_threshold=2.0, dominance_ratio=1.5)

    assert classify_scores({"V": 5.0, "T": 4.0, "I": 0.2}, True, settings)["channel"] == "multi"
    assert classify_scores({"V": 0.2, "T": 0.5, "I": 0.1}, True, settings)["channel"] == "unknown"
    assert classify_scores({"V": 9.0, "T": 0.5, "I": 0.1}, False, settings)["channel"] == "none"
    assert classify_scores({}, False, settings, command_tampered=True)["channel"] == "command"


def test_ekf_single_channel_updates_preserve_valid_covariance() -> None:
    config = get_config()
    ekf = EKF(config)
    ekf.initialize(3.7, 35.0)
    ekf.predict(30.0)

    v_residual, v_std = ekf.update_channel("V", 3.71, 30.0)
    t_residual, t_std = ekf.update_channel("T", 36.0, 30.0)

    assert math.isfinite(v_residual)
    assert math.isfinite(t_residual)
    assert v_std > 0.0 and t_std > 0.0
    assert ekf.P.diagonal().min() > 0.0


def test_localization_engine_supports_command_override_and_reset() -> None:
    engine = LocalizationEngine(get_config())
    first = engine.update(3.7, 0.0, 35.0, 0.0, alarm=False)
    command = engine.update(3.7, 0.0, 35.0, 0.0, alarm=True, command_tampered=True)

    assert first["channel"] == "none"
    assert command["channel"] == "command"
    assert command["confidence"] == 1.0
    engine.reset()
    assert engine.update(3.7, 0.0, 35.0, 0.0, alarm=False)["channel"] == "none"


def test_localization_settings_load_from_project_config() -> None:
    settings = load_localization_config()

    assert settings.window_s == pytest.approx(60.0)
    assert settings.score_threshold > 0.0
    assert settings.dominance_ratio > 1.0


def test_confusion_matrix_marks_multi_as_ambiguous_except_all_channel_attacks() -> None:
    single_channel = confusion_matrix(["temp", "temp"], ["multi", "temp"], scenario_id="AT2")
    all_channels = confusion_matrix(["multi"], ["multi"], scenario_id="AT4")

    assert single_channel["ambiguous_multi"] == 1
    assert single_channel["accuracy_excluding_ambiguous"] == pytest.approx(1.0)
    assert all_channels["ambiguous_multi"] == 0
    assert all_channels["accuracy_excluding_ambiguous"] == pytest.approx(1.0)
