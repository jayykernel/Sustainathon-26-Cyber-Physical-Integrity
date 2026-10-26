"""P3 attack-interface, knowledge-boundary, and scenario-catalog tests."""

import numpy as np
import pytest

from physiguard.attacks.base import (
    AttackContext,
    OracleContext,
    ReplayContext,
    load_attack_definitions,
    make_attack,
)
from physiguard.attacks.runner import run_attack_scenario
from physiguard.attacks.scenarios import load_scenarios
from physiguard.config import get_config
from physiguard.plant import Plant


def _telemetry() -> dict[str, float]:
    return {"V_rep": 3.7, "I_rep": 30.0, "T_rep": 35.0}


def _truth() -> dict[str, float]:
    return {"soc_true": 0.5, "V_true": 3.7, "T_true": 35.0}


def test_attack_definitions_and_scenario_catalog_are_complete() -> None:
    onset_range, definitions = load_attack_definitions()
    catalog = load_scenarios()

    assert onset_range == (600, 1500)
    assert set(definitions) == {f"AT{i}" for i in range(1, 7)}
    assert {scenario.id for scenario in catalog.scenarios} == {
        "baseline",
        "spike",
        "drift",
        "replay",
        "model_synthesis",
        "malicious_command",
        "oracle_limit",
    }
    assert catalog.story_ladder


def test_attack_onset_is_deterministic_and_within_configured_range() -> None:
    first = make_attack("AT1", get_config(), seed=25)
    second = make_attack("AT1", get_config(), seed=25)

    assert first.onset_s == second.onset_s
    assert 600 <= first.onset_s <= 1500


def test_at1_spikes_are_bursty_and_below_static_limits() -> None:
    attack = make_attack("AT1", get_config(), seed=7)
    result = attack.apply(
        attack.onset_s,
        _truth(),
        _telemetry(),
        attack.rng,
        AttackContext(),
    )
    later = attack.apply(
        attack.onset_s + 5,
        _truth(),
        _telemetry(),
        attack.rng,
        AttackContext(),
    )

    assert result["T_rep"] == pytest.approx(47.0)
    assert 3.0 <= result["V_rep"] <= 4.3
    assert later["T_rep"] == pytest.approx(35.0)


def test_at2_drift_rate_matches_half_degree_per_minute() -> None:
    attack = make_attack("AT2", get_config(), seed=2)
    at_onset = attack.apply(
        attack.onset_s, _truth(), _telemetry(), attack.rng, AttackContext()
    )
    one_minute_later = attack.apply(
        attack.onset_s + 60, _truth(), _telemetry(), attack.rng, AttackContext()
    )

    assert at_onset["T_rep"] == pytest.approx(35.0)
    assert one_minute_later["T_rep"] == pytest.approx(34.5)


def test_at3_replays_old_telemetry_and_degrades_cooling() -> None:
    attack = make_attack("AT3", get_config(), seed=3)
    recorded = {
        "V_rep": np.array([3.5, 3.6, 3.7]),
        "I_rep": np.array([10.0, 20.0, 30.0]),
        "T_rep": np.array([35.0, 36.0, 37.0]),
    }
    context = ReplayContext(recorded)
    time_s = attack.onset_s + 301
    result = attack.apply(time_s, _truth(), _telemetry(), attack.rng, context)
    plant = Plant(get_config())
    attack.physical(time_s, plant)

    replay_index = int(time_s - 300) % 3
    assert result["V_rep"] == pytest.approx(recorded["V_rep"][replay_index])
    assert result["T_rep"] == pytest.approx(recorded["T_rep"][replay_index])
    assert plant.thermal_resistance_multiplier == pytest.approx(2.5)


def test_at4_cannot_read_truth_command_or_oracle_context() -> None:
    class ForbiddenTruth(dict[str, float]):
        def __getitem__(self, key: str) -> float:
            if key == "I_cmd":
                raise AssertionError("AT4 attempted to read I_cmd")
            return super().__getitem__(key)

    class ForbiddenContext(AttackContext):
        def __getattribute__(self, name: str) -> object:
            if name in {"I_cmd", "delta_I", "probe"}:
                raise AssertionError(f"AT4 attempted to read oracle field {name}")
            return super().__getattribute__(name)

    attack = make_attack("AT4", get_config(), seed=4)
    result = attack.apply(
        attack.onset_s,
        ForbiddenTruth(_truth()),
        _telemetry(),
        attack.rng,
        ForbiddenContext(),
    )

    assert all(np.isfinite(value) for value in result.values())
    assert not hasattr(AttackContext, "I_cmd")


def test_at6_requires_and_uses_the_oracle_command() -> None:
    attack = make_attack("AT6", get_config(), seed=6)
    result = attack.apply(
        attack.onset_s,
        _truth(),
        _telemetry(),
        attack.rng,
        OracleContext(I_cmd=80.0),
    )

    assert result["I_rep"] == pytest.approx(80.0, abs=0.5)
    with pytest.raises(ValueError, match="oracle I_cmd"):
        attack.apply(attack.onset_s, _truth(), _telemetry(), attack.rng, AttackContext())


def test_at5_forces_150_a_only_after_soc_crossing_and_seeded_delay() -> None:
    attack = make_attack("AT5", get_config(), seed=13)
    assert attack.request(10, 70.0, {**_truth(), "soc_true": 0.84}) == 70.0
    assert attack.request(20, 70.0, {**_truth(), "soc_true": 0.85}) == 70.0
    assert attack.attack_start_s is not None
    before = max(20.0, attack.attack_start_s - 1.0)
    assert attack.request(before, 70.0, _truth()) == 70.0
    assert attack.request(attack.attack_start_s, 70.0, _truth()) == 150.0
    assert attack.config.charger.I_rated >= 150.0


def test_at5_command_attack_reaches_voltage_or_soc_hazard() -> None:
    config = get_config()
    trajectory = run_attack_scenario("AT5", seed=17, config=config, duration_s=3600)
    hazard = (trajectory["V_true"] > config.plant.V_hazard) | (
        trajectory["soc_true"] > 1.02
    )

    assert np.any(hazard & trajectory["attack_active"])


@pytest.mark.parametrize("attack_id", ["AT1", "AT2", "AT3", "AT4", "AT5"])
def test_at1_to_at5_outputs_respect_applicable_static_limits(attack_id: str) -> None:
    config = get_config()
    trajectory = run_attack_scenario(attack_id, seed=17, config=config, duration_s=3600)

    assert np.all((-5.0 <= trajectory["I_rep"]) & (
        trajectory["I_rep"] <= config.plant.I_rated + 5.0
    ))
    assert np.all((0 <= trajectory["I_req"]) & (
        trajectory["I_req"] <= config.plant.I_rated
    ))
    if attack_id != "AT5":
        assert np.all((config.plant.V_min - 0.5 <= trajectory["V_rep"]) & (
            trajectory["V_rep"] <= config.plant.V_hazard
        ))
    if attack_id in {"AT2", "AT3", "AT4", "AT5"}:
        assert np.all((config.plant.T_amb - 20 <= trajectory["T_rep"]) & (
            trajectory["T_rep"] <= config.plant.T_hazard
        ))
