"""Ground-truth two-RC battery plant from SPEC section 2.

Current is positive while charging. Temperatures are in °C, time in seconds,
current in amperes, voltage in volts, and resistance in ohms.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from .config import Config, get_config

logger = logging.getLogger(__name__)

_OCV_TABLE: NDArray[np.float64] = np.array(
    [3.00, 3.30, 3.45, 3.55, 3.62, 3.68, 3.75, 3.82, 3.92, 4.05, 4.20],
    dtype=np.float64,
)
_SOC_POINTS: NDArray[np.float64] = np.linspace(0.0, 1.0, len(_OCV_TABLE))


class PlantStep(TypedDict):
    """Plant state and terminal voltage after one step."""

    soc: float
    v1: float
    v2: float
    T: float
    v_term: float


PlantTrajectory = dict[str, NDArray[np.float64]]


def ocv_lookup(
    soc: float | NDArray[np.float64], offset_v: float = 0.0
) -> float | NDArray[np.float64]:
    """Return piecewise-linear open-circuit voltage for SOC in [0, 1]."""
    soc_clipped = np.clip(soc, 0.0, 1.0)
    voltage = np.interp(soc_clipped, _SOC_POINTS, _OCV_TABLE) + offset_v
    if np.isscalar(soc):
        return float(voltage)
    return np.asarray(voltage, dtype=np.float64)


def resistance_r0(config: Config, temperature_c: float) -> float:
    """Return the temperature-adjusted ohmic resistance in ohms."""
    return config.plant.R0_ref * (1.0 + config.plant.a_R * (25.0 - temperature_c))


def plant_step(
    soc: float,
    v1: float,
    v2: float,
    temperature_c: float,
    current_a: float,
    config: Config,
    ambient_c: float | None = None,
    dt_s: float | None = None,
    thermal_resistance_multiplier: float = 1.0,
) -> tuple[float, float, float, float]:
    """Advance SOC, RC polarization, and temperature for one time step."""
    if ambient_c is None:
        ambient_c = config.plant.T_amb
    if dt_s is None:
        dt_s = config.simulation.dt

    p = config.plant
    if not np.isfinite(thermal_resistance_multiplier) or thermal_resistance_multiplier <= 0:
        raise ValueError("thermal_resistance_multiplier must be finite and positive")
    r0 = resistance_r0(config, temperature_c)
    soc_new = max(0.0, soc + p.eta * current_a * dt_s / (3600.0 * p.Q))

    decay1 = np.exp(-dt_s / p.tau1)
    decay2 = np.exp(-dt_s / p.tau2)
    v1_new = v1 * decay1 + p.R1 * (1.0 - decay1) * current_a
    v2_new = v2 * decay2 + p.R2 * (1.0 - decay2) * current_a

    heat_w = current_a**2 * (r0 + p.R1 + p.R2)
    temperature_new = temperature_c + dt_s / p.C_th * (
        heat_w - (temperature_c - ambient_c) / (p.R_th * thermal_resistance_multiplier)
    )
    return float(soc_new), float(v1_new), float(v2_new), float(temperature_new)


def plant_advance(
    current_profile_a: NDArray[np.float64],
    config: Config | None = None,
    ambient_profile_c: NDArray[np.float64] | None = None,
    seed: int | None = None,
) -> PlantTrajectory:
    """Simulate a plant trajectory; seeded calls reproduce sensor-noise arrays."""
    if config is None:
        config = get_config()

    current_profile_a = np.asarray(current_profile_a, dtype=np.float64)
    if current_profile_a.ndim != 1 or not np.all(np.isfinite(current_profile_a)):
        raise ValueError("current_profile_a must be a finite one-dimensional array")

    if ambient_profile_c is None:
        ambient_profile_c = np.full(current_profile_a.shape, config.plant.T_amb)
    else:
        ambient_profile_c = np.asarray(ambient_profile_c, dtype=np.float64)
        if ambient_profile_c.shape != current_profile_a.shape:
            raise ValueError("ambient_profile_c must have the same shape as current_profile_a")
        if not np.all(np.isfinite(ambient_profile_c)):
            raise ValueError("ambient_profile_c must contain only finite values")

    n_steps = current_profile_a.size
    soc = float(config.plant.SOC_0)
    temperature_c = float(
        config.plant.T_0 if config.plant.T_0 is not None else config.plant.T_amb
    )
    v1 = 0.0
    v2 = 0.0
    dt_s = float(config.simulation.dt)

    soc_traj = np.empty(n_steps, dtype=np.float64)
    v1_traj = np.empty(n_steps, dtype=np.float64)
    v2_traj = np.empty(n_steps, dtype=np.float64)
    temperature_traj = np.empty(n_steps, dtype=np.float64)
    voltage_traj = np.empty(n_steps, dtype=np.float64)

    for index, current_a in enumerate(current_profile_a):
        ambient_c = float(ambient_profile_c[index])
        soc, v1, v2, temperature_c = plant_step(
            soc,
            v1,
            v2,
            temperature_c,
            float(current_a),
            config,
            ambient_c,
            dt_s,
        )
        soc_traj[index] = soc
        v1_traj[index] = v1
        v2_traj[index] = v2
        temperature_traj[index] = temperature_c
        voltage_traj[index] = (
            float(ocv_lookup(soc, config.plant.OCV_offset))
            + float(current_a) * resistance_r0(config, temperature_c)
            + v1
            + v2
        )

    result: PlantTrajectory = {
        "soc": soc_traj,
        "v1": v1_traj,
        "v2": v2_traj,
        "t": np.arange(n_steps, dtype=np.float64) * dt_s,
        "T": temperature_traj,
        "v_term": voltage_traj,
        "I_profile": current_profile_a.copy(),
        "T_amb_profile": ambient_profile_c.copy(),
    }

    if seed is not None:
        rng = np.random.default_rng(seed)
        result["V_noise"] = rng.normal(0.0, config.sensors.V_sigma, n_steps)
        result["I_noise"] = rng.normal(0.0, config.sensors.I_sigma, n_steps)
        result["T_noise"] = rng.normal(0.0, config.sensors.T_sigma, n_steps)

    if n_steps:
        logger.info(
            "Plant advance complete: %d steps, SOC range [%.3f, %.3f], temperature range [%.1f, %.1f] °C",
            n_steps,
            float(np.min(soc_traj)),
            float(np.max(soc_traj)),
            float(np.min(temperature_traj)),
            float(np.max(temperature_traj)),
        )
    return result


class Plant:
    """Stateful plant instance for step-by-step simulation."""

    def __init__(self, config: Config | None = None, seed: int | None = None) -> None:
        self.config = config or get_config()
        self.seed = seed
        self.soc = 0.0
        self.v1 = 0.0
        self.v2 = 0.0
        self.temperature_c = 0.0
        self.current_a = 0.0
        self.thermal_resistance_multiplier = 1.0
        self.reset()

    def reset(self) -> None:
        """Restore the configured initial SOC and temperature."""
        self.soc = float(self.config.plant.SOC_0)
        self.temperature_c = float(
            self.config.plant.T_0
            if self.config.plant.T_0 is not None
            else self.config.plant.T_amb
        )
        self.v1 = 0.0
        self.v2 = 0.0
        self.current_a = 0.0
        self.thermal_resistance_multiplier = 1.0

    def set_cooling_degradation(self, thermal_resistance_multiplier: float) -> None:
        """Set a persistent cooling fault as a multiplier on thermal resistance."""
        if not np.isfinite(thermal_resistance_multiplier) or thermal_resistance_multiplier < 1.0:
            raise ValueError("cooling degradation multiplier must be finite and at least 1")
        self.thermal_resistance_multiplier = thermal_resistance_multiplier

    def step(self, current_a: float, ambient_c: float | None = None) -> PlantStep:
        """Advance by one step and return true state and terminal voltage."""
        if ambient_c is None:
            ambient_c = self.config.plant.T_amb
        self.soc, self.v1, self.v2, self.temperature_c = plant_step(
            self.soc,
            self.v1,
            self.v2,
            self.temperature_c,
            current_a,
            self.config,
            ambient_c,
            thermal_resistance_multiplier=self.thermal_resistance_multiplier,
        )
        self.current_a = current_a
        return {
            "soc": self.soc,
            "v1": self.v1,
            "v2": self.v2,
            "T": self.temperature_c,
            "v_term": self.get_terminal_voltage(),
        }

    def advance(self, current_profile_a: NDArray[np.float64]) -> PlantTrajectory:
        """Simulate an independent trajectory using this instance's config and seed."""
        return plant_advance(current_profile_a, self.config, seed=self.seed)

    def get_terminal_voltage(self) -> float:
        """Return terminal voltage in volts at the current plant state."""
        return float(
            ocv_lookup(self.soc, self.config.plant.OCV_offset)
            + self.current_a * resistance_r0(self.config, self.temperature_c)
            + self.v1
            + self.v2
        )


def vary_unit_config(config: Config, seed: int) -> Config:
    """Return a reproducible plant config with configured unit-to-unit variation."""
    varied = deepcopy(config)
    rng = np.random.default_rng(seed)
    p = varied.plant
    p.Q *= 1.0 + rng.uniform(-p.Q_var_pct, p.Q_var_pct) / 100.0
    p.R0_ref *= 1.0 + rng.uniform(-p.R0_var_pct, p.R0_var_pct) / 100.0
    p.R1 *= 1.0 + rng.uniform(-p.R1_var_pct, p.R1_var_pct) / 100.0
    p.R_th *= 1.0 + rng.uniform(-p.R_th_var_pct, p.R_th_var_pct) / 100.0
    p.OCV_offset = rng.uniform(-p.OCV_offset_mV, p.OCV_offset_mV) / 1000.0
    varied._config_hash = varied.config_hash()
    return varied
