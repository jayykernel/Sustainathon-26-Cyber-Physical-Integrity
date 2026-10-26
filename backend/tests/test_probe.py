"""Keyed probe generation, safe clipping, scheduling, and gain regression tests."""

import numpy as np
import pytest

from physiguard.config import get_config
from physiguard.detectors.gain import (
    estimate_gain,
    evaluate_gain_window,
    expected_voltage_response,
    load_gain_thresholds,
)
from physiguard.detectors.probe import (
    ProbeScheduler,
    generate_probe_window,
    is_probe_current_safe,
)
from physiguard.plant import Plant


def test_probe_is_balanced_keyed_and_nonce_specific() -> None:
    config = get_config()
    args = (90.0, 90.0, 120)
    first = generate_probe_window(*args, key="test-key", nonce=b"nonce-0000000001", config=config)
    repeat = generate_probe_window(*args, key="test-key", nonce=b"nonce-0000000001", config=config)
    fresh = generate_probe_window(*args, key="test-key", nonce=b"nonce-0000000002", config=config)

    assert first.delta_I.mean() == pytest.approx(0.0, abs=1e-12)
    assert np.array_equal(first.delta_I, repeat.delta_I)
    assert not np.array_equal(first.delta_I, fresh.delta_I)
    assert np.all(np.isin(first.delta_I, (-first.amplitude_a, first.amplitude_a)))


def test_probe_clips_safely_to_current_and_thermal_headroom() -> None:
    config = get_config()
    plant = Plant(config)
    window = generate_probe_window(
        90.0, 90.0, 120, key="safety", nonce=b"safe-window-0001", config=config, plant=plant
    )
    assert window.amplitude_a <= 3.6
    assert all(is_probe_current_safe(90.0 + delta, plant, config) for delta in window.delta_I)

    plant.temperature_c = config.plant.T_warn + 1.0
    inhibited = generate_probe_window(
        90.0, 90.0, 120, key="safety", nonce=b"safe-window-0002", config=config, plant=plant
    )
    assert inhibited.amplitude_a == 0.0


def test_probe_scheduler_uses_periodic_and_continuous_windows_with_fresh_nonces() -> None:
    scheduler = ProbeScheduler(get_config(), seed=17)

    assert scheduler.is_active(0.0)
    assert scheduler.is_active(719.0)
    assert not scheduler.is_active(720.0)
    assert scheduler.nonce_for(0.0) == scheduler.nonce_for(119.0)
    assert scheduler.nonce_for(600.0) != scheduler.nonce_for(0.0)
    assert scheduler.is_active(120.0, "SUSPECT")
    assert scheduler.nonce_for(0.0, "SUSPECT") != scheduler.nonce_for(120.0, "SUSPECT")


def test_authentic_probe_gain_is_near_one_in_voltage_current_and_combined() -> None:
    config = get_config()
    probe = generate_probe_window(
        90.0, 90.0, 120, key="gain-key", nonce=b"gain-window-0001", config=config
    )
    voltage_expected = expected_voltage_response(probe.delta_I, config)
    rng = np.random.default_rng(12)
    voltage = voltage_expected + rng.normal(0.0, config.sensors.V_sigma, 120)
    current = probe.delta_I + rng.normal(0.0, config.sensors.I_sigma, 120)
    decision = evaluate_gain_window(voltage, current, probe.delta_I, config)

    assert decision.voltage.gain == pytest.approx(1.0, abs=0.4)
    assert decision.current.gain == pytest.approx(1.0, abs=0.03)
    assert not decision.detected_voltage
    assert not decision.detected_current
    assert not decision.detected_combined


def test_replay_of_previous_probe_has_low_gain_for_fresh_challenge() -> None:
    config = get_config()
    previous = generate_probe_window(
        90.0, 90.0, 120, key="gain-key", nonce=b"old-window-00001", config=config
    )
    current = generate_probe_window(
        90.0, 90.0, 120, key="gain-key", nonce=b"new-window-00002", config=config
    )
    old_voltage = expected_voltage_response(previous.delta_I, config)
    observed = old_voltage + np.random.default_rng(4).normal(0, config.sensors.V_sigma, 120)
    replay_gain = estimate_gain(observed, expected_voltage_response(current.delta_I, config),
                                config.sensors.V_sigma, config=config)

    assert replay_gain.gain < config.probe.g_min_V


def test_calibrated_gain_thresholds_validate_the_config_hash(tmp_path) -> None:
    config = get_config()
    path = tmp_path / "probe-calibration.yaml"
    path.write_text(
        f"config_hash: {config.config_hash()}\ng_min_V: 0.4\ng_min_I: 0.7\n",
        encoding="utf-8",
    )

    assert load_gain_thresholds(config, path) == pytest.approx((0.4, 0.7))
    path.write_text("config_hash: mismatched\ng_min_V: 0.4\ng_min_I: 0.7\n", encoding="utf-8")
    with pytest.raises(ValueError, match="different config hash"):
        load_gain_thresholds(config, path)
