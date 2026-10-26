"""Unit tests for sensor noise and charger behavior."""

import pytest

from physiguard.charger import ChargeProfile, execute_request, thermal_derate_factor
from physiguard.config import Config
from physiguard.sensors import Sensors


def test_sensors_are_seeded_and_quantized() -> None:
    config = Config()
    first = Sensors(config, seed=23).read(4.0, 15.0, 35.0)
    second = Sensors(config, seed=23).read(4.0, 15.0, 35.0)

    assert first == second
    assert first["V_rep"] / config.sensors.V_quant == pytest.approx(
        round(first["V_rep"] / config.sensors.V_quant)
    )
    assert first["I_rep"] / config.sensors.I_quant == pytest.approx(
        round(first["I_rep"] / config.sensors.I_quant)
    )


def test_charger_derates_from_reported_temperature_and_caps_current() -> None:
    config = Config()
    assert thermal_derate_factor(39.0, config) == pytest.approx(1.0)
    assert thermal_derate_factor(45.0, config) == pytest.approx(0.6)
    assert thermal_derate_factor(51.0, config) == pytest.approx(0.2)
    assert execute_request(200.0, 30.0, config) == pytest.approx(config.charger.I_rated)
    assert execute_request(150.0, 50.0, config) == pytest.approx(30.0)


def test_profile_latches_into_constant_voltage_mode() -> None:
    config = Config()
    profile = ChargeProfile(config)

    assert profile.request(4.19) == config.charger.I_fast
    assert profile.request(4.20) == pytest.approx(0.0)
    assert profile.in_cv_phase
    assert profile.request(4.10) == pytest.approx(20.0)
    assert profile.in_cv_phase
