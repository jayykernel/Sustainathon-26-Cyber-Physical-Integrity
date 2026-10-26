"""Minimal closed-loop integration of battery, sensors, and charger."""

from __future__ import annotations

from typing import TypedDict, cast

import numpy as np
from numpy.typing import NDArray

from .charger import ChargeProfile, execute_request
from .config import Config, get_config
from .plant import Plant, vary_unit_config
from .sensors import Sensors


class PipelineTrajectory(TypedDict):
    """Aligned sampled true state, telemetry, and controller signals."""

    t: NDArray[np.float64]
    soc_true: NDArray[np.float64]
    V_true: NDArray[np.float64]
    T_true: NDArray[np.float64]
    V_rep: NDArray[np.float64]
    I_rep: NDArray[np.float64]
    T_rep: NDArray[np.float64]
    I_req: NDArray[np.float64]
    I_cmd: NDArray[np.float64]
    hijack_active: NDArray[np.bool_]


def run_pipeline(
    config: Config | None = None,
    seed: int = 0,
    duration_s: int | None = None,
    underreport_temperature: bool = False,
    hijack_cv_current_a: float | None = None,
    unit_variation: bool = True,
) -> PipelineTrajectory:
    """Run the honest CC/CV loop with optional documented attack injections."""
    base_config = config or get_config()
    if duration_s is None:
        duration_s = base_config.simulation.duration
    if duration_s < 0:
        raise ValueError("duration_s must be non-negative")
    run_config = vary_unit_config(base_config, seed) if unit_variation else base_config
    plant = Plant(run_config)
    sensors = Sensors(run_config, seed + 1)
    profile = ChargeProfile(run_config)
    previous_current = 0.0
    in_cv_phase = False

    keys = ("t", "soc_true", "V_true", "T_true", "V_rep", "I_rep", "T_rep", "I_req", "I_cmd")
    values: dict[str, list[float]] = {key: [] for key in keys}
    attack_values: list[bool] = []

    for index in range(duration_s):
        pre_readings = sensors.read(
            plant.get_terminal_voltage(), previous_current, plant.temperature_c
        )
        requested = profile.request(pre_readings["V_rep"])
        in_cv_phase = in_cv_phase or profile.in_cv_phase
        hijack_active = hijack_cv_current_a is not None and in_cv_phase
        if hijack_cv_current_a is not None and in_cv_phase:
            requested = hijack_cv_current_a
        reported_temperature = 30.0 if underreport_temperature else pre_readings["T_rep"]
        applied = execute_request(requested, reported_temperature, run_config)
        state = plant.step(applied)

        post_readings = sensors.read(state["v_term"], applied, state["T"])
        if underreport_temperature:
            post_readings["T_rep"] = 30.0
        sample = {
            "t": index * float(run_config.simulation.dt),
            "soc_true": state["soc"],
            "V_true": state["v_term"],
            "T_true": state["T"],
            "V_rep": post_readings["V_rep"],
            "I_rep": post_readings["I_rep"],
            "T_rep": post_readings["T_rep"],
            "I_req": requested,
            "I_cmd": applied,
        }
        for key, value in sample.items():
            values[key].append(value)
        attack_values.append(hijack_active)
        previous_current = applied

    result = cast(
        PipelineTrajectory,
        {key: np.asarray(series, dtype=np.float64) for key, series in values.items()},
    )
    result["hijack_active"] = np.asarray(attack_values, dtype=np.bool_)
    return result
