"""Closed-loop P1 reproducibility and plausibility acceptance tests."""

import numpy as np

from physiguard.config import Config
from physiguard.pipeline import run_paired_pipeline, run_pipeline
from physiguard.plant import plant_advance, vary_unit_config


def test_pipeline_is_deterministic_for_a_seed() -> None:
    first = run_pipeline(Config(), seed=101, duration_s=90)
    second = run_pipeline(Config(), seed=101, duration_s=90)

    assert first.keys() == second.keys()
    for key in first:
        np.testing.assert_array_equal(first[key], second[key])


def test_paired_attack_pipeline_reuses_seed_and_returns_guard_evidence() -> None:
    undefended, defended = run_paired_pipeline("AT4", seed=17, duration_s=90)

    assert undefended["t"].shape == defended["t"].shape == (90,)
    np.testing.assert_array_equal(undefended["t"], defended["t"])
    assert not undefended["defended"]
    assert defended["defended"]
    assert defended["response_state"].shape == (90,)
    assert defended["command_unsafe"].shape == (90,)
    assert defended["probe_active"].shape == (90,)
    assert np.any(np.abs(defended["probe_delta"]) > 0.0)
    assert isinstance(defended["events"], list)


def test_honest_one_hour_run_stays_within_operating_limits() -> None:
    config = Config()
    result = run_pipeline(config, seed=11, duration_s=3600, unit_variation=False)

    assert np.all(np.diff(result["soc_true"]) >= 0)
    assert result["T_true"].max() < config.plant.T_warn
    assert result["V_true"].min() >= config.plant.V_min
    assert result["V_true"].max() <= config.plant.V_max + 0.02


def test_underreported_temperature_reaches_hazard_within_25_minutes() -> None:
    config = Config()
    result = run_pipeline(
        config,
        seed=11,
        duration_s=1500,
        underreport_temperature=True,
        unit_variation=False,
    )
    hazards = np.flatnonzero(result["T_true"] > config.plant.T_hazard)

    assert hazards.size
    assert hazards[0] * config.simulation.dt <= 25 * 60
    assert np.all(result["T_rep"] == 30.0)


def test_hijacked_cv_request_reaches_voltage_or_soc_hazard_within_five_minutes() -> None:
    config = Config()
    result = run_pipeline(
        config,
        seed=11,
        duration_s=3600,
        hijack_cv_current_a=150.0,
        unit_variation=False,
    )
    active = np.flatnonzero(result["hijack_active"])
    assert active.size
    hazard = (result["V_true"] > config.plant.V_hazard) | (
        result["soc_true"] > 1.02
    )
    reached = np.flatnonzero(hazard & result["hijack_active"])

    assert reached.size
    assert (reached[0] - active[0]) * config.simulation.dt <= 5 * 60


def test_two_hundred_varied_units_have_finite_trajectories() -> None:
    config = Config()
    current = np.resize(np.array([0.0, 25.0, 90.0, 45.0]), 120)
    for seed in range(200):
        unit = vary_unit_config(config, seed)
        trajectory = plant_advance(current, unit)
        assert all(np.all(np.isfinite(array)) for array in trajectory.values())
