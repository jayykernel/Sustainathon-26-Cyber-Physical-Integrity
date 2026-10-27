"""Seeded noisy and quantized telemetry sensors."""

from __future__ import annotations

from typing import TypedDict

import numpy as np

from .config import Config, get_config


class SensorReadings(TypedDict):
    """Voltage, current, and temperature telemetry from one sample."""

    V_rep: float
    I_rep: float
    T_rep: float


class Sensors:
    """Independent sensor noise source with deterministic seeded output."""

    def __init__(self, config: Config | None = None, seed: int | None = None) -> None:
        self.config = config or get_config()
        self.rng = np.random.default_rng(seed)

    def read(self, voltage_v: float, current_a: float, temperature_c: float) -> SensorReadings:
        """Add configured Gaussian noise and round readings to sensor resolution."""
        c = self.config.sensors
        return {
            "V_rep": self._quantize(voltage_v + self.rng.normal(0.0, c.V_sigma), c.V_quant),
            "I_rep": self._quantize(current_a + self.rng.normal(0.0, c.I_sigma), c.I_quant),
            "T_rep": self._quantize(
                temperature_c + self.rng.normal(0.0, c.T_sigma), c.T_quant
            ),
        }

    @staticmethod
    def _quantize(value: float, resolution: float) -> float:
        return float(round(value / resolution) * resolution)
