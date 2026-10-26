"""Regression tests for the ground-truth battery plant."""

import numpy as np
import pytest

from physiguard.config import Config
from physiguard.plant import Plant, ocv_lookup, plant_advance


def test_ocv_is_monotone_and_clips_out_of_range_soc() -> None:
    """OCV follows the configured table and stays bounded beyond SOC limits."""
    soc = np.linspace(0.0, 1.0, 101)
    voltage = ocv_lookup(soc)

    assert np.all(np.diff(voltage) > 0)
    assert ocv_lookup(-0.2) == pytest.approx(3.0)
    assert ocv_lookup(1.2) == pytest.approx(4.2)


def test_plant_advance_conserves_charge_and_is_seed_reproducible() -> None:
    """Positive current increases SOC by eta*I*dt/(3600*Q), deterministically."""
    config = Config()
    profile = np.full(120, 30.0)
    first = plant_advance(profile, config, seed=42)
    second = plant_advance(profile, config, seed=42)

    expected_delta = config.plant.eta * 30.0 * 120 / (3600.0 * config.plant.Q)
    assert first["soc"][-1] - config.plant.SOC_0 == pytest.approx(expected_delta)
    assert np.all(np.diff(first["soc"]) > 0)
    for key in first:
        np.testing.assert_array_equal(first[key], second[key])


def test_plant_thermal_steady_state_matches_analytic_solution() -> None:
    """At constant current with fixed resistance, thermal rise matches I²R R_th."""
    config = Config()
    config.plant.a_R = 0.0
    config.plant.T_amb = 25.0
    current_a = 10.0
    result = plant_advance(np.full(20_000, current_a), config)

    resistance = config.plant.R0_ref + config.plant.R1 + config.plant.R2
    expected_rise = current_a**2 * resistance * config.plant.R_th
    assert result["T"][-1] - config.plant.T_amb == pytest.approx(
        expected_rise, rel=0.01
    )


def test_plant_instance_voltage_uses_last_applied_current() -> None:
    """The terminal-voltage accessor agrees with the most recent step output."""
    plant = Plant(Config())
    result = plant.step(25.0)

    assert plant.get_terminal_voltage() == pytest.approx(result["v_term"])


def test_plant_rejects_mismatched_ambient_profile() -> None:
    """Malformed environmental input is rejected before simulation starts."""
    with pytest.raises(ValueError, match="same shape"):
        plant_advance(np.ones(3), ambient_profile_c=np.ones(2))
