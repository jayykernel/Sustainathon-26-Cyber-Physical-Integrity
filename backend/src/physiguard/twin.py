"""One-RC digital twin and extended Kalman filter.

State order is [SOC, V1, T], with current in amperes and temperature in °C.
"""

from __future__ import annotations

import logging
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from .config import Config, get_config

logger = logging.getLogger(__name__)


def twin_ocv_lookup(soc: float, config: Config) -> float:
    """Interpolate the twin's configured OCV table at a bounded SOC."""
    ocv_values = np.asarray(config.twin.OCV_n, dtype=np.float64)
    soc_points = np.linspace(0.0, 1.0, ocv_values.size)
    return float(np.interp(np.clip(soc, 0.0, 1.0), soc_points, ocv_values))


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
        decay = np.exp(-dt_s / p.tau1_n)
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
        self.R = np.diag(
            [
                self.config.sensors.V_sigma**2,
                self.config.sensors.T_sigma**2,
            ]
        ).astype(np.float64) * R_ekf_inflation
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

    def predict(
        self, current_a: float, ambient_hat_c: float | None = None
    ) -> NDArray[np.float64]:
        """Propagate the state and covariance by one time step."""
        if not self.initialized:
            raise ModelError("EKF is not initialized; call initialize() first")
        if ambient_hat_c is None:
            ambient_hat_c = float(self.config.twin.T_amb_hat)

        dt_s = float(self.config.simulation.dt)
        p = self.config.twin
        soc, v1, temperature_c = self.x
        decay = np.exp(-dt_s / p.tau1_n)
        soc_new = soc + self.config.plant.eta * current_a * dt_s / (3600.0 * p.Q_n)
        v1_new = v1 * decay + p.R1_n * (1.0 - decay) * current_a
        heat_w = current_a**2 * (p.R0_n + p.R1_n)
        temperature_new = temperature_c + dt_s / p.C_th_n * (
            heat_w - (temperature_c - ambient_hat_c) / p.R_th_n
        )
        self.x = np.array([soc_new, v1_new, temperature_new], dtype=np.float64)

        transition = np.diag(
            [1.0, decay, 1.0 - dt_s / (p.C_th_n * p.R_th_n)]
        ).astype(np.float64)
        self.P = transition @ self.P @ transition.T + self.Q
        self.P = 0.5 * (self.P + self.P.T)
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
        predicted = np.array(
            [twin_ocv_lookup(soc, self.config) + I_cmd * p.R0_n + v1, temperature_c],
            dtype=np.float64,
        )
        measurement = np.array([V_meas, T_meas], dtype=np.float64)
        innovation = measurement - predicted
        H = np.array(
            [[self._d_ocv_d_soc(soc), 1.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        S = H @ self.P @ H.T + self.R
        try:
            solved_innovation = np.linalg.solve(S, innovation)
            gain = np.linalg.solve(S, H @ self.P).T
        except np.linalg.LinAlgError as exc:
            raise NumericalError("Innovation covariance is singular") from exc

        nis = float(innovation @ solved_innovation)
        identity = np.eye(3, dtype=np.float64)
        residual_map = identity - gain @ H
        self.P = residual_map @ self.P @ residual_map.T + gain @ self.R @ gain.T
        self.P = 0.5 * (self.P + self.P.T)
        self.x = self.x + gain @ innovation

        if I_meas is None:
            I_meas = (V_meas - twin_ocv_lookup(self.x[0], self.config) - self.x[1]) / p.R0_n
        current_residual = float(I_meas - I_cmd)
        self.r_I_history.append(current_residual)
        return {
            "x_updated": self.x.copy(),
            "P_updated": self.P.copy(),
            "nu": innovation,
            "innovation_std": np.sqrt(np.diag(S)),
            "NIS": nis,
            "r_I": current_residual,
        }

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

    def compute_NIS(self, V_meas: float, T_meas: float, I_cmd: float) -> tuple[float, NDArray[np.float64]]:
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
