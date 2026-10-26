"""Safety guard, response hysteresis, and trust-aware virtual sensor tests."""

from copy import deepcopy

import numpy as np

from physiguard.command_guard import CommandGuard
from physiguard.config import Config
from physiguard.response import ResponseManager, VirtualSensor
from physiguard.twin import Twin


def test_command_guard_bisects_unsafe_current_to_a_pessimistic_limit() -> None:
    config = Config()
    guard = CommandGuard(config)
    result = guard.evaluate(150.0, np.array([0.7, 0.0, config.plant.T_warn - 1.0]))

    assert result.unsafe
    assert 0.0 <= result.safe_current_a < 150.0
    assert result.applied_request_a == result.safe_current_a
    assert result.predicted_max_temperature_c > config.plant.T_warn


def test_command_guard_closed_form_horizon_matches_twin_steps() -> None:
    config = Config()
    state = np.array([0.7, 0.02, 38.0])
    current = 75.0
    pessimistic = deepcopy(config)
    pessimistic.twin.R_th_n *= config.command_guard.R_th_pessimism
    pessimistic.twin.T_amb_hat += config.command_guard.T_amb_pessimism
    pessimistic.twin.R0_n *= config.command_guard.R0_pessimism
    twin = Twin(pessimistic)
    twin.x = state.copy()
    predictions = [twin.step(current) for _ in range(config.command_guard.horizon)]
    assert twin.x is not None

    maxima = CommandGuard(config)._predict(pessimistic, state, current)
    assert maxima[0] >= max(float(value[0]) for value in predictions)
    assert maxima[1] >= max(float(value[1]) for value in predictions)
    assert maxima[2] >= float(twin.x[0])


def test_response_requires_independent_evidence_and_persistence() -> None:
    response = ResponseManager(Config())
    assert response.update(0.0, {"passive_NIS"}).state == "SUSPECT"
    assert response.update(20.0, {"passive_NIS"}).state == "SUSPECT"
    assert response.update(30.0, {"CUSUM"}).state == "CONFIRMED"
    assert response.update(39.0).state == "CONFIRMED"
    assert response.update(40.0).state == "SAFE_MODE"
    assert [event["code"] for event in response.events] == [
        "suspect",
        "confirmed",
        "safe_mode",
    ]


def test_suspect_state_does_not_oscillate_back_without_operator_action() -> None:
    response = ResponseManager(Config())
    assert response.update(5.0, {"CUSUM"}).state == "SUSPECT"
    assert response.update(5.0 + 10_000.0).state == "SUSPECT"


def test_two_failed_probe_windows_confirm_and_safe_mode_needs_operator_reset() -> None:
    response = ResponseManager(Config())
    assert response.update(1.0, probe_failed=True).state == "SUSPECT"
    assert response.update(2.0, probe_failed=True).state == "CONFIRMED"
    assert response.update(12.0).state == "SAFE_MODE"
    assert response.request_operator_reset(12.0)
    for time_s in (13.0, 14.0, 15.0):
        state = response.update(time_s, clean_challenge=True).state
    assert state == "NORMAL"
    assert response.events[-1]["code"] == "operator_reset"


def test_virtual_sensor_marks_all_flagged_channels_degraded_and_recovers() -> None:
    config = Config()
    sensor = VirtualSensor(config)
    _, quality = sensor.update(3.8, 31.0, 50.0)
    assert quality == "normal"
    _, quality = sensor.update(3.9, 40.0, 50.0, {"V", "I", "T"})
    assert quality == "degraded"
    assert sensor.state.shape == (3,)
    _, quality = sensor.update(3.9, 32.0, 50.0)
    assert quality == "normal"
