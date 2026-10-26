"""Undefended closed-loop execution harness for attack scenarios."""

from __future__ import annotations

from typing import TypedDict, cast

import numpy as np
from numpy.typing import NDArray

from ..charger import ChargeProfile, execute_request
from ..config import Config, get_config, load_detection_config
from ..detectors.passive import PassiveDetectors
from ..pipeline import run_pipeline
from ..plant import Plant, vary_unit_config
from ..sensors import Sensors
from ..twin import EKF
from .base import AttackContext, OracleContext, ReplayContext, Telemetry, TruthState, make_attack


class AttackTrajectory(TypedDict):
    """Sampled truth, forged telemetry, control signals, and passive alarms."""

    t: NDArray[np.float64]
    soc_true: NDArray[np.float64]
    V_true: NDArray[np.float64]
    T_true: NDArray[np.float64]
    V_rep: NDArray[np.float64]
    I_rep: NDArray[np.float64]
    T_rep: NDArray[np.float64]
    I_req: NDArray[np.float64]
    I_cmd: NDArray[np.float64]
    attack_active: NDArray[np.bool_]
    B0_alarm: NDArray[np.bool_]
    B1_alarm: NDArray[np.bool_]
    B2_alarm: NDArray[np.bool_]
    CUSUM_V_alarm: NDArray[np.bool_]
    CUSUM_T_alarm: NDArray[np.bool_]
    CUSUM_I_alarm: NDArray[np.bool_]


def run_attack_scenario(
    attack_id: str,
    seed: int,
    config: Config | None = None,
    duration_s: int | None = None,
    attack_config_path: str | None = None,
) -> AttackTrajectory:
    """Simulate one deterministic, undefended attack run and B0/B1/B2 monitors."""
    base_config = config or get_config()
    if duration_s is None:
        duration_s = base_config.simulation.duration
    if duration_s < 1:
        raise ValueError("duration_s must be at least one second")
    detection = load_detection_config(base_config=base_config)
    run_config = vary_unit_config(base_config, seed)
    run_config.detection = detection
    attack = make_attack(attack_id, run_config, seed, attack_config_path)
    plant = Plant(run_config)
    sensors = Sensors(run_config, seed + 1)
    profile = ChargeProfile(run_config)
    monitor = PassiveDetectors(run_config)
    ekf = EKF(run_config)
    previous_current_a = 0.0

    replay_ctx: ReplayContext | None = None
    if attack_id == "AT3":
        clean = run_pipeline(
            run_config,
            seed=seed,
            duration_s=duration_s,
            unit_variation=False,
        )
        replay_ctx = ReplayContext(
            telemetry={
                "V_rep": clean["V_rep"],
                "I_rep": clean["I_rep"],
                "T_rep": clean["T_rep"],
            }
        )

    keys = (
        "t",
        "soc_true",
        "V_true",
        "T_true",
        "V_rep",
        "I_rep",
        "T_rep",
        "I_req",
        "I_cmd",
    )
    samples: dict[str, list[float]] = {key: [] for key in keys}
    active_values: list[bool] = []
    b0_values: list[bool] = []
    b1_values: list[bool] = []
    b2_values: list[bool] = []
    cusum_values: dict[str, list[bool]] = {channel: [] for channel in ("V", "T", "I")}

    for index in range(duration_s):
        t_s = index * float(run_config.simulation.dt)
        truth: TruthState = {
            "soc_true": plant.soc,
            "V_true": plant.get_terminal_voltage(),
            "T_true": plant.temperature_c,
        }
        raw: Telemetry = sensors.read(
            truth["V_true"], previous_current_a, truth["T_true"]
        )
        if attack_id == "AT6":
            attack_context: AttackContext = OracleContext(I_cmd=previous_current_a)
        elif replay_ctx is not None:
            attack_context = replay_ctx
        else:
            attack_context = AttackContext()
        reported = attack.apply(t_s, truth, raw, attack.rng, attack_context)

        if index == 0:
            ekf.initialize(reported["V_rep"], reported["T_rep"])
            passive_alarms: set[str] = set()
        else:
            ekf.predict(previous_current_a)
            update = ekf.update(
                reported["V_rep"],
                reported["T_rep"],
                previous_current_a,
                I_meas=reported["I_rep"],
            )
            decision = monitor.update(
                update["NIS"],
                update["nu"],
                update["innovation_std"],
                update["r_I"],
                reported["V_rep"],
                reported["I_rep"],
                reported["T_rep"],
            )
            passive_alarms = decision["alarms"]

        for channel in cusum_values:
            cusum_values[channel].append(f"CUSUM_{channel}" in passive_alarms)

        requested = profile.request(reported["V_rep"])
        requested = attack.request(t_s, requested, truth)
        attack.physical(t_s, plant)
        applied = execute_request(requested, reported["T_rep"], run_config)
        b0_alarm = any(alarm.startswith("RANGE_") for alarm in passive_alarms)
        b1_alarm = "NIS" in passive_alarms
        b2_alarm = b1_alarm or any(alarm.startswith("CUSUM_") for alarm in passive_alarms)

        state = {
            "t": t_s,
            "soc_true": truth["soc_true"],
            "V_true": truth["V_true"],
            "T_true": truth["T_true"],
            "V_rep": reported["V_rep"],
            "I_rep": reported["I_rep"],
            "T_rep": reported["T_rep"],
            "I_req": requested,
            "I_cmd": applied,
        }
        for key, value in state.items():
            samples[key].append(value)
        active_values.append(attack.is_active(t_s))
        b0_values.append(b0_alarm)
        b1_values.append(b1_alarm)
        b2_values.append(b2_alarm)

        plant.step(applied)
        previous_current_a = applied

    return cast(
        AttackTrajectory,
        {
            **{key: np.asarray(values, dtype=np.float64) for key, values in samples.items()},
            "attack_active": np.asarray(active_values, dtype=np.bool_),
            "B0_alarm": np.asarray(b0_values, dtype=np.bool_),
            "B1_alarm": np.asarray(b1_values, dtype=np.bool_),
            "B2_alarm": np.asarray(b2_values, dtype=np.bool_),
            "CUSUM_V_alarm": np.asarray(cusum_values["V"], dtype=np.bool_),
            "CUSUM_T_alarm": np.asarray(cusum_values["T"], dtype=np.bool_),
            "CUSUM_I_alarm": np.asarray(cusum_values["I"], dtype=np.bool_),
        },
    )
