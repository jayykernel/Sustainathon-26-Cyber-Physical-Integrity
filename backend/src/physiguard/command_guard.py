"""Pessimistic forward-simulation guard for requested charging current."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import exp

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
        self._limit_configs: dict[bool, Config] = {}
        self._prediction_parameters: dict[int, tuple[Config, tuple[float, ...]]] = {}
        for worst_case, multiplier in (
            (False, float(self.config.command_guard.R_th_pessimism)),
            (True, float(self.config.command_guard.R_th_worst)),
        ):
            limit_config = deepcopy(self.config)
            limit_config.twin.R_th_n *= multiplier
            limit_config.twin.T_amb_hat += float(self.config.command_guard.T_amb_pessimism)
            limit_config.twin.R0_n *= float(self.config.command_guard.R0_pessimism)
            self._limit_configs[worst_case] = limit_config
            self._cache_prediction_parameters(limit_config)

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
        limit_config = self._limit_configs[worst_case]

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
        soc, v1, temperature = map(float, state)
        (
            soc_per_amp,
            rc_decay_n,
            rc_current_gain,
            r0,
            heat_resistance,
            thermal_decay_n,
            ambient,
        ) = self._prediction_parameters_for(config)
        v1_end = v1 * rc_decay_n + rc_current_gain * current_a
        soc_end = soc + soc_per_amp * current_a
        equilibrium = ambient + current_a**2 * heat_resistance
        temp_end = equilibrium + (temperature - equilibrium) * thermal_decay_n
        # SOC/OCV and RC voltage are monotone under a constant non-negative
        # request; the independent maxima give a conservative voltage envelope.
        voltage_max = (
            twin_ocv_lookup(soc_end, config) + current_a * r0 + max(v1, v1_end)
        )
        # Keep the analytical envelope conservative across accumulated float
        # rounding in the step-by-step twin used by the plant.
        numerical_margin = 1e-9
        return (
            voltage_max + numerical_margin,
            max(temperature, temp_end) + numerical_margin,
            max(soc, soc_end) + numerical_margin,
        )

    def _cache_prediction_parameters(self, config: Config) -> tuple[float, ...]:
        """Precompute request-independent horizon factors for repeated guard checks."""
        steps = max(1, int(np.ceil(config.command_guard.horizon / config.simulation.dt)))
        dt_s = float(config.simulation.dt)
        p = config.twin
        rc_decay_n = exp(-dt_s / p.tau1_n) ** steps
        thermal_decay_n = (1.0 - dt_s / (p.C_th_n * p.R_th_n)) ** steps
        parameters = (
            config.plant.eta * dt_s * steps / (3600.0 * p.Q_n),
            rc_decay_n,
            p.R1_n * (1.0 - rc_decay_n),
            p.R0_n,
            (p.R0_n + p.R1_n) * p.R_th_n,
            thermal_decay_n,
            p.T_amb_hat,
        )
        self._prediction_parameters[id(config)] = (config, parameters)
        return parameters

    def _prediction_parameters_for(self, config: Config) -> tuple[float, ...]:
        cached = self._prediction_parameters.get(id(config))
        if cached is None or cached[0] is not config:
            return self._cache_prediction_parameters(config)
        return cached[1]

    def _safe(self, voltage_v: float, temperature_c: float, soc: float) -> bool:
        p = self.config.plant
        return (
            voltage_v <= float(p.V_max)
            and temperature_c <= float(p.T_warn)
            and soc <= 1.0
        )
