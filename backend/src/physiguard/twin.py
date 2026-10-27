"""One-RC digital twin and extended Kalman filter.

State order is [SOC, V1, T], with current in amperes and temperature in °C.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from math import exp, isnan
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from .config import Config, get_config

logger = logging.getLogger(__name__)


_OCV_GRID_CACHE: dict[int, tuple[list[float], tuple[float, ...]]] = {}


@lru_cache(maxsize=64)
def _decay(dt_s: float, tau_s: float) -> float:
    return exp(-dt_s / tau_s)


def twin_ocv_lookup(soc: float, config: Config) -> float:
    """Interpolate the twin's configured OCV table at a bounded SOC."""
    values = config.twin.OCV_n
    cached = _OCV_GRID_CACHE.get(id(values))
    if cached is None or cached[0] is not values:
        cached = (values, tuple(float(value) for value in values))
        _OCV_GRID_CACHE[id(values)] = cached
    _, ocv_values = cached
    scalar_soc = float(soc)
    if isnan(scalar_soc):
        return float("nan")
    bounded_soc = min(1.0, max(0.0, scalar_soc))
    position = bounded_soc * (len(ocv_values) - 1)
    lower = min(int(position), len(ocv_values) - 2)
    fraction = position - lower
    return float(ocv_values[lower] + fraction * (ocv_values[lower + 1] - ocv_values[lower]))


class EKFUpdate(TypedDict):
    """Measurement update results used by detectors and diagnostics."""

    x_updated: NDArray[np.float64]
    P_updated: NDArray[np.float64]
    nu: NDArray[np.float64]
    innovation_std: NDArray[np.float64]
    NIS: float
    r_I: float


class Twin:
    """One-RC battery model used for forward predictions."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self.x: NDArray[np.float64] | None = None
        self.reset()

    def reset(self) -> None:
        """Restore SOC, polarization voltage, and temperature to initial values."""
        self.x = np.array(
            [
                float(self.config.plant.SOC_0),
                0.0,
                float(self.config.twin.T_amb_hat),
            ],
            dtype=np.float64,
        )

    def step(self, current_a: float, ambient_hat_c: float | None = None) -> NDArray[np.float64]:
        """Advance the twin by one configured time step and return [V, T]."""
        if self.x is None:
            raise ModelError("Twin state is not initialized; call reset() first")
        if ambient_hat_c is None:
            ambient_hat_c = float(self.config.twin.T_amb_hat)

        dt_s = float(self.config.simulation.dt)
        p = self.config.twin
        soc, v1, temperature_c = self.x
        decay = _decay(dt_s, float(p.tau1_n))
        soc_new = soc + self.config.plant.eta * current_a * dt_s / (3600.0 * p.Q_n)
        v1_new = v1 * decay + p.R1_n * (1.0 - decay) * current_a
        heat_w = current_a**2 * (p.R0_n + p.R1_n)
        temperature_new = temperature_c + dt_s / p.C_th_n * (
            heat_w - (temperature_c - ambient_hat_c) / p.R_th_n
        )
        self.x = np.array([soc_new, v1_new, temperature_new], dtype=np.float64)

        voltage = twin_ocv_lookup(soc_new, self.config) + current_a * p.R0_n + v1_new
        return np.array([voltage, temperature_new], dtype=np.float64)


class EKF:
    """Extended Kalman filter for the one-RC twin, using a Joseph covariance update."""

    def __init__(
        self,
        config: Config | None = None,
        Q_ekf: NDArray[np.float64] | None = None,
        R_ekf_inflation: float = 1.0,
    ) -> None:
        self.config = config or get_config()
        if R_ekf_inflation <= 0:
            raise ValueError("R_ekf_inflation must be positive")
        self.Q = (
            np.asarray(Q_ekf, dtype=np.float64)
            if Q_ekf is not None
            else np.diag([1e-6, 1e-5, 1e-3]).astype(np.float64)
        )
        if self.Q.shape != (3, 3):
            raise ValueError("Q_ekf must have shape (3, 3)")
        self.R = (
            np.diag(
                [
                    self.config.sensors.V_sigma**2,
                    self.config.sensors.T_sigma**2,
                ]
            ).astype(np.float64)
            * R_ekf_inflation
        )
        dt_s = float(self.config.simulation.dt)
        decay = _decay(dt_s, float(self.config.twin.tau1_n))
        thermal_decay = 1.0 - dt_s / (
            self.config.twin.C_th_n * self.config.twin.R_th_n
        )
        transition = np.array([1.0, decay, thermal_decay], dtype=np.float64)
        self._transition_outer = np.outer(transition, transition)
        self._dt_s = dt_s
        self._decay = decay
        self.P = np.diag([0.25**2, 0.1**2, 2.0**2]).astype(np.float64)
        self.x = np.zeros(3, dtype=np.float64)
        self.initialized = False
        self.r_I_history: list[float] = []

    def initialize(self, V_meas: float, T_meas: float) -> None:
        """Initialize SOC by inverting OCV; start polarization voltage at zero."""
        ocv_values = np.asarray(self.config.twin.OCV_n, dtype=np.float64)
        soc_points = np.linspace(0.0, 1.0, ocv_values.size)
        soc = float(np.interp(V_meas, ocv_values, soc_points))
        self.x = np.array([soc, 0.0, T_meas], dtype=np.float64)
        self.initialized = True

    def predict(self, current_a: float, ambient_hat_c: float | None = None) -> NDArray[np.float64]:
        """Propagate the state and covariance by one time step."""
        if not self.initialized:
            raise ModelError("EKF is not initialized; call initialize() first")
        if ambient_hat_c is None:
            ambient_hat_c = float(self.config.twin.T_amb_hat)

        p = self.config.twin
        soc, v1, temperature_c = self.x
        decay = self._decay
        dt_s = self._dt_s
        soc_new = soc + self.config.plant.eta * current_a * dt_s / (3600.0 * p.Q_n)
        v1_new = v1 * decay + p.R1_n * (1.0 - decay) * current_a
        heat_w = current_a**2 * (p.R0_n + p.R1_n)
        temperature_new = temperature_c + dt_s / p.C_th_n * (
            heat_w - (temperature_c - ambient_hat_c) / p.R_th_n
        )
        self.x[0], self.x[1], self.x[2] = soc_new, v1_new, temperature_new
        # The transition matrix is diagonal and constant for this configuration.
        self.P *= self._transition_outer
        self.P += self.Q
        return self.x.copy()

    def update(
        self,
        V_meas: float,
        T_meas: float,
        I_cmd: float,
        I_meas: float | None = None,
    ) -> EKFUpdate:
        """Apply a voltage/temperature measurement and return innovation diagnostics."""
        if not self.initialized:
            raise ModelError("EKF is not initialized; call initialize() first")

        soc, v1, temperature_c = self.x
        p = self.config.twin
        innovation_v = V_meas - (twin_ocv_lookup(soc, self.config) + I_cmd * p.R0_n + v1)
        innovation_t = T_meas - temperature_c
        h = self._d_ocv_d_soc(soc)
        # The observation matrix has rows [h, 1, 0] and [0, 0, 1], so form
        # its 2x2 covariance and solve it without allocating matrix objects.
        p00, p01, p02 = (float(value) for value in self.P[0])
        p11, p12 = float(self.P[1, 1]), float(self.P[1, 2])
        p22 = float(self.P[2, 2])
        s00 = h * h * p00 + 2.0 * h * p01 + p11 + float(self.R[0, 0])
        s01 = h * p02 + p12
        s11 = p22 + float(self.R[1, 1])
        determinant = s00 * s11 - s01 * s01
        if not np.isfinite(determinant) or determinant <= 0.0:
            raise NumericalError("Innovation covariance is singular")
        inv00, inv01, inv11 = s11 / determinant, -s01 / determinant, s00 / determinant
        solved_v = inv00 * innovation_v + inv01 * innovation_t
        solved_t = inv01 * innovation_v + inv11 * innovation_t
        hp00, hp01, hp02 = h * p00 + p01, h * p01 + p11, h * p02 + p12
        hp10, hp11, hp12 = p02, p12, p22
        k00, k01 = hp00 * inv00 + hp10 * inv01, hp00 * inv01 + hp10 * inv11
        k10, k11 = hp01 * inv00 + hp11 * inv01, hp01 * inv01 + hp11 * inv11
        k20, k21 = hp02 * inv00 + hp12 * inv01, hp02 * inv01 + hp12 * inv11
        nis = innovation_v * solved_v + innovation_t * solved_t

        # P-KHP is algebraically equivalent to the Joseph update for this
        # optimal gain. Update its six independent entries directly.
        new_p00 = p00 - (k00 * hp00 + k01 * hp10)
        new_p01 = p01 - (k00 * hp01 + k01 * hp11)
        new_p02 = p02 - (k00 * hp02 + k01 * hp12)
        new_p11 = p11 - (k10 * hp01 + k11 * hp11)
        new_p12 = p12 - (k10 * hp02 + k11 * hp12)
        new_p22 = p22 - (k20 * hp02 + k21 * hp12)
        self.P[0, 0] = new_p00
        self.P[0, 1] = self.P[1, 0] = new_p01
        self.P[0, 2] = self.P[2, 0] = new_p02
        self.P[1, 1] = new_p11
        self.P[1, 2] = self.P[2, 1] = new_p12
        self.P[2, 2] = new_p22
        self.x[0] = soc + k00 * innovation_v + k01 * innovation_t
        self.x[1] = v1 + k10 * innovation_v + k11 * innovation_t
        self.x[2] = temperature_c + k20 * innovation_v + k21 * innovation_t

        if I_meas is None:
            I_meas = (V_meas - twin_ocv_lookup(self.x[0], self.config) - self.x[1]) / p.R0_n
        current_residual = float(I_meas - I_cmd)
        self.r_I_history.append(current_residual)
        return {
            "x_updated": self.x.copy(),
            "P_updated": self.P.copy(),
            "nu": np.array([innovation_v, innovation_t], dtype=np.float64),
            "innovation_std": np.array([np.sqrt(s00), np.sqrt(s11)], dtype=np.float64),
            "NIS": nis,
            "r_I": current_residual,
        }

    def update_channel(self, channel: str, measurement: float, I_cmd: float) -> tuple[float, float]:
        """Update one measurement channel for cross-prediction EKF banks."""
        if not self.initialized:
            raise ModelError("EKF is not initialized; call initialize() first")
        if channel not in {"V", "T"}:
            raise ValueError("channel must be 'V' or 'T'")
        if not np.isfinite(measurement) or not np.isfinite(I_cmd):
            raise ValueError("measurement and I_cmd must be finite")

        soc, v1, temperature_c = self.x
        if channel == "V":
            p = self.config.twin
            h = self._d_ocv_d_soc(soc)
            predicted = twin_ocv_lookup(soc, self.config) + I_cmd * p.R0_n + v1
            variance = float(self.R[0, 0])
            p00, p01, p02 = (float(value) for value in self.P[0])
            p11, p12 = float(self.P[1, 1]), float(self.P[1, 2])
            p22 = float(self.P[2, 2])
            ph0, ph1, ph2 = h * p00 + p01, h * p01 + p11, h * p02 + p12
            innovation = measurement - predicted
            covariance = h * ph0 + ph1 + variance
        else:
            predicted = temperature_c
            variance = float(self.R[1, 1])
            p00, p01, p02 = (float(value) for value in self.P[0])
            p11, p12 = float(self.P[1, 1]), float(self.P[1, 2])
            p22 = float(self.P[2, 2])
            ph0, ph1, ph2 = p02, p12, p22
            innovation = measurement - predicted
            covariance = ph2 + variance
        if not np.isfinite(covariance) or covariance <= 0:
            raise NumericalError("Single-channel innovation covariance is invalid")
        gain0, gain1, gain2 = ph0 / covariance, ph1 / covariance, ph2 / covariance
        self.P[0, 0] = p00 - gain0 * ph0
        self.P[0, 1] = self.P[1, 0] = p01 - gain0 * ph1
        self.P[0, 2] = self.P[2, 0] = p02 - gain0 * ph2
        self.P[1, 1] = p11 - gain1 * ph1
        self.P[1, 2] = self.P[2, 1] = p12 - gain1 * ph2
        self.P[2, 2] = p22 - gain2 * ph2
        self.x[0] = soc + gain0 * innovation
        self.x[1] = v1 + gain1 * innovation
        self.x[2] = temperature_c + gain2 * innovation
        return float(innovation), float(np.sqrt(covariance))

    def _d_ocv_d_soc(self, soc: float) -> float:
        """Estimate dOCV/dSOC with a bounded central or one-sided difference."""
        delta = 0.01
        lower = max(0.0, soc - delta)
        upper = min(1.0, soc + delta)
        if upper == lower:
            return 0.0
        return float(
            (twin_ocv_lookup(upper, self.config) - twin_ocv_lookup(lower, self.config))
            / (upper - lower)
        )

    def compute_NIS(
        self, V_meas: float, T_meas: float, I_cmd: float
    ) -> tuple[float, NDArray[np.float64]]:
        """Return an NIS diagnostic while restoring the filter state afterward."""
        state = self.x.copy()
        covariance = self.P.copy()
        initialized = self.initialized
        history_length = len(self.r_I_history)
        try:
            if not self.initialized:
                self.initialize(V_meas, T_meas)
            self.predict(I_cmd)
            result = self.update(V_meas, T_meas, I_cmd)
            return result["NIS"], result["nu"]
        finally:
            self.x = state
            self.P = covariance
            self.initialized = initialized
            del self.r_I_history[history_length:]


class ModelError(Exception):
    """Raised when a model operation is attempted in an invalid state."""


class NumericalError(ModelError):
    """Raised when EKF covariance math is singular or otherwise invalid."""
