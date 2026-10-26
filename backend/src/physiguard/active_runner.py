"""Attack simulation with scheduled, safety-clipped active probe windows."""

from __future__ import annotations

from typing import TypedDict, cast

import numpy as np
from numpy.typing import NDArray

from .attacks.base import (
    AttackBase,
    AttackContext,
    OracleContext,
    ReplayContext,
    Telemetry,
    TruthState,
    make_attack,
)
from .charger import ChargeProfile, execute_request
from .config import Config, get_config, load_detection_config
from .detectors.passive import PassiveDetectors
from .detectors.probe import (
    ProbeScheduler,
    ProbeWindow,
    generate_probe_window,
    is_probe_current_safe,
)
from .pipeline import run_pipeline
from .plant import Plant, vary_unit_config
from .sensors import Sensors
from .twin import EKF


class ActiveTrajectory(TypedDict):
    """Attack signals and monitor outputs aligned to each one-second step."""

    t: NDArray[np.float64]
    soc_true: NDArray[np.float64]
    V_true: NDArray[np.float64]
    T_true: NDArray[np.float64]
    V_rep: NDArray[np.float64]
    I_rep: NDArray[np.float64]
    T_rep: NDArray[np.float64]
    I_req: NDArray[np.float64]
    I_base_cmd: NDArray[np.float64]
    I_cmd: NDArray[np.float64]
    probe_delta: NDArray[np.float64]
    probe_active: NDArray[np.bool_]
    attack_active: NDArray[np.bool_]
    B0_alarm: NDArray[np.bool_]
    B1_alarm: NDArray[np.bool_]
    B2_alarm: NDArray[np.bool_]


def run_active_scenario(
    attack_id: str,
    seed: int,
    amplitude_pct: float | None = None,
    config: Config | None = None,
    duration_s: int | None = None,
    probe_key: str | None = None,
) -> ActiveTrajectory:
    """Run one undefended scenario with NORMAL-mode periodic probe windows."""
    base = config or get_config()
    duration = duration_s if duration_s is not None else base.simulation.duration
    if duration < 1:
        raise ValueError("duration_s must be at least one second")
    detection = load_detection_config(base_config=base)
    run_config = vary_unit_config(base, seed)
    run_config.detection = detection
    attack: AttackBase | None = None
    if attack_id != "baseline":
        attack = make_attack(attack_id, run_config, seed)
    plant = Plant(run_config)
    sensors = Sensors(run_config, seed + 1)
    profile = ChargeProfile(run_config)
    passive = PassiveDetectors(run_config)
    ekf = EKF(run_config)
    scheduler = ProbeScheduler(run_config, seed + 2)
    key = probe_key or run_config.probe.key or f"validation-probe-key-{seed}"
    previous_current = 0.0
    replay: ReplayContext | None = None
    if attack_id == "AT3":
        clean = run_pipeline(run_config, seed=seed, duration_s=duration, unit_variation=False)
        replay = ReplayContext(
            telemetry={name: clean[name] for name in ("V_rep", "I_rep", "T_rep")}
        )

    scalar_names = (
        "t",
        "soc_true",
        "V_true",
        "T_true",
        "V_rep",
        "I_rep",
        "T_rep",
        "I_req",
        "I_base_cmd",
        "I_cmd",
        "probe_delta",
    )
    values: dict[str, list[float]] = {name: [] for name in scalar_names}
    probe_flags: list[bool] = []
    attack_flags: list[bool] = []
    b0: list[bool] = []
    b1: list[bool] = []
    b2: list[bool] = []
    challenge_key: tuple[int, int] | None = None
    challenge: ProbeWindow | None = None

    for index in range(duration):
        time_s = index * float(run_config.simulation.dt)
        truth: TruthState = {
            "soc_true": plant.soc,
            "V_true": plant.get_terminal_voltage(),
            "T_true": plant.temperature_c,
        }
        raw: Telemetry = sensors.read(truth["V_true"], previous_current, truth["T_true"])
        if attack_id == "AT6":
            context: AttackContext = OracleContext(I_cmd=previous_current)
        elif replay is not None:
            context = replay
        else:
            context = AttackContext()
        reported = (
            attack.apply(time_s, truth, raw, attack.rng, context)
            if attack is not None
            else raw
        )

        if index == 0:
            ekf.initialize(reported["V_rep"], reported["T_rep"])
            alarms: set[str] = set()
        else:
            ekf.predict(previous_current)
            update = ekf.update(
                reported["V_rep"], reported["T_rep"], previous_current, I_meas=reported["I_rep"]
            )
            alarms = passive.update(
                update["NIS"],
                update["nu"],
                update["innovation_std"],
                update["r_I"],
                reported["V_rep"],
                reported["I_rep"],
                reported["T_rep"],
            )["alarms"]

        requested = profile.request(reported["V_rep"])
        if attack is not None:
            requested = attack.request(time_s, requested, truth)
            attack.physical(time_s, plant)
        baseline_current = execute_request(requested, reported["T_rep"], run_config)
        active = scheduler.is_active(time_s, "NORMAL")
        delta_current = 0.0
        if active:
            window_index = scheduler.window_index(time_s, "NORMAL")
            window_start_s = window_index * run_config.probe.period
            start_index = int(round(window_start_s / run_config.simulation.dt))
            offset = index - start_index
            current_key = (window_index, start_index)
            if challenge_key != current_key:
                nonce = scheduler.nonce_for(time_s, "NORMAL")
                if nonce is None:
                    raise RuntimeError("active probe window has no nonce")
                challenge = generate_probe_window(
                    baseline_current,
                    requested,
                    int(round(run_config.probe.window / run_config.simulation.dt)),
                    key=key,
                    nonce=nonce,
                    config=run_config,
                    plant=plant,
                    amplitude_pct=amplitude_pct,
                )
                challenge_key = current_key
            if challenge is None or not 0 <= offset < challenge.delta_I.size:
                raise RuntimeError("probe schedule and challenge window are inconsistent")
            proposed_delta = float(challenge.delta_I[offset])
            if is_probe_current_safe(baseline_current + proposed_delta, plant, run_config):
                delta_current = proposed_delta

        applied = baseline_current + delta_current
        values["t"].append(time_s)
        values["soc_true"].append(truth["soc_true"])
        values["V_true"].append(truth["V_true"])
        values["T_true"].append(truth["T_true"])
        values["V_rep"].append(reported["V_rep"])
        values["I_rep"].append(reported["I_rep"])
        values["T_rep"].append(reported["T_rep"])
        values["I_req"].append(requested)
        values["I_base_cmd"].append(baseline_current)
        values["I_cmd"].append(applied)
        values["probe_delta"].append(delta_current)
        probe_flags.append(active and delta_current != 0.0)
        attack_flags.append(attack.is_active(time_s) if attack is not None else False)
        b0.append(any(name.startswith("RANGE_") for name in alarms))
        b1.append("NIS" in alarms)
        b2.append("NIS" in alarms or any(name.startswith("CUSUM_") for name in alarms))
        plant.step(applied)
        previous_current = applied

    return cast(
        ActiveTrajectory,
        {
            **{name: np.asarray(items, dtype=np.float64) for name, items in values.items()},
            "probe_active": np.asarray(probe_flags, dtype=np.bool_),
            "attack_active": np.asarray(attack_flags, dtype=np.bool_),
            "B0_alarm": np.asarray(b0, dtype=np.bool_),
            "B1_alarm": np.asarray(b1, dtype=np.bool_),
            "B2_alarm": np.asarray(b2, dtype=np.bool_),
        },
    )
