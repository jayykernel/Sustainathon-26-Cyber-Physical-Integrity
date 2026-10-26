"""Active attack-runner probe alignment and safety smoke checks."""

import numpy as np
import pytest

from physiguard.active_runner import run_active_scenario
from physiguard.config import get_config


def test_active_runner_applies_a_balanced_safe_probe_window() -> None:
    config = get_config()
    trace = run_active_scenario("baseline", seed=9, config=config, duration_s=120)

    assert trace["probe_active"].all()
    assert trace["probe_delta"].mean() == pytest.approx(0.0, abs=1e-12)
    assert np.all((0.0 <= trace["I_cmd"]) & (trace["I_cmd"] <= config.plant.I_rated))
    assert np.max(trace["V_true"]) < config.plant.V_max
    assert np.max(trace["T_true"]) < config.plant.T_warn


def test_zero_amplitude_active_runner_matches_unprobed_current() -> None:
    trace = run_active_scenario("baseline", seed=9, amplitude_pct=0.0, duration_s=120)

    assert np.all(trace["probe_delta"] == 0.0)
    assert not trace["probe_active"].any()
    assert np.allclose(trace["I_cmd"], trace["I_base_cmd"])
