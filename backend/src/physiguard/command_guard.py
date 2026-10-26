"""Pessimistic forward-simulation guard for requested charging current."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .config import Config, get_config
from .twin import twin_ocv_lookup


@dataclass(frozen=True)
class GuardResult:
    """Safe current recommendation and the requested-current prediction."""

    requested_current_a: float
    safe_current_a: float
    applied_request_a: float
    unsafe: bool
    violation: bool
    predicted_max_voltage_v: float
    predicted_max_temperature_c: float
    predicted_max_soc: float


class CommandGuard:
    """Limit current when the pessimistic twin predicts a configured limit breach."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()

    def evaluate(
        self,
        requested_current_a: float,
        state: NDArray[np.float64] | tuple[float, float, float] | list[float],
        *,
        worst_case: bool = False,
    ) -> GuardResult:
        """Predict a constant request for H seconds and bisect to a safe limit."""
        if not np.isfinite(requested_current_a) or requested_current_a < 0:
            raise ValueError("requested current must be finite and non-negative")
        initial = np.asarray(state, dtype=np.float64)
        if initial.shape != (3,) or not np.all(np.isfinite(initial)):
            raise ValueError("state must be a finite [SOC, V1, temperature] vector")
        c = self.config
        requested = min(float(requested_current_a), float(c.charger.I_rated))
        limit_config = deepcopy(c)
        limit_config.twin.R_th_n *= (
            float(c.command_guard.R_th_worst)
            if worst_case
            else float(c.command_guard.R_th_pessimism)
        )
        limit_config.twin.T_amb_hat += float(c.command_guard.T_amb_pessimism)
        limit_config.twin.R0_n *= float(c.command_guard.R0_pessimism)

        requested_prediction = self._predict(limit_config, initial, requested)
        violation = not self._safe(*requested_prediction)
        if violation:
            low, high = 0.0, requested
            for _ in range(int(c.command_guard.bisection_max_iter)):
                candidate = 0.5 * (low + high)
                if self._safe(*self._predict(limit_config, initial, candidate)):
                    low = candidate
                else:
                    high = candidate
            safe = low
        else:
            safe = requested
        return GuardResult(
            requested_current_a=float(requested_current_a),
            safe_current_a=float(safe),
            applied_request_a=float(min(requested, safe)),
            unsafe=bool(violation),
            violation=bool(violation),
            predicted_max_voltage_v=requested_prediction[0],
            predicted_max_temperature_c=requested_prediction[1],
            predicted_max_soc=requested_prediction[2],
        )

    def _predict(
        self, config: Config, state: NDArray[np.float64], current_a: float
    ) -> tuple[float, float, float]:
        # The requested current is held constant, so SOC, RC polarization, and
        # temperature each have a closed-form horizon prediction matching Twin.step.
        steps = max(1, int(np.ceil(config.command_guard.horizon / config.simulation.dt)))
        dt_s = float(config.simulation.dt)
        p = config.twin
        soc, v1, temperature = map(float, state)
        decay_rc = float(np.exp(-dt_s / p.tau1_n))
        r0 = p.R0_n
        heat_w = current_a**2 * (r0 + p.R1_n)
        thermal_decay = 1.0 - dt_s / (p.C_th_n * p.R_th_n)
        equilibrium = p.T_amb_hat + heat_w * p.R_th_n

        def prediction_at(step: int) -> tuple[float, float, float]:
            soc_at = soc + config.plant.eta * current_a * dt_s * step / (
                3600.0 * p.Q_n
            )
            decay_n = decay_rc**step
            v1_at = v1 * decay_n + p.R1_n * (1.0 - decay_n) * current_a
            temp_at = equilibrium + (temperature - equilibrium) * thermal_decay**step
            voltage = (
                twin_ocv_lookup(soc_at, config) + current_a * r0 + v1_at
            )
            return voltage, temp_at, soc_at

        first = prediction_at(1)
        last = prediction_at(steps)
        return (
            max(first[0], last[0]),
            max(first[1], last[1]),
            max(first[2], last[2]),
        )

    def _safe(self, voltage_v: float, temperature_c: float, soc: float) -> bool:
        p = self.config.plant
        return (
            voltage_v <= float(p.V_max)
            and temperature_c <= float(p.T_warn)
            and soc <= 1.0
        )
