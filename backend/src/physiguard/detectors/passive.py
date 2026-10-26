"""Combined NIS, per-channel CUSUM, and range-based passive monitor."""

from __future__ import annotations

from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from ..config import Config, get_config
from .cusum import CUSUM
from .nis import NISWindow
from .range_check import RangeCheck


class PassiveResult(TypedDict):
    """Per-sample alarm names and normalized residuals."""

    alarms: set[str]
    z: dict[str, float]
    nis_window_sum: float | None


class PassiveDetectors:
    """Run three passive test families on a shared telemetry stream."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        d = self.config.detection
        self.nis = NISWindow(d.NIS_window, d.NIS_threshold)
        self.cusum = {
            channel: CUSUM(d.CUSUM_kappa, d.CUSUM_h, d.CUSUM_deadband)
            for channel in ("V", "T", "I")
        }
        self.range = RangeCheck(self.config)

    def reset(self) -> None:
        """Reset all detector state between independent simulation runs."""
        self.nis.reset()
        for detector in self.cusum.values():
            detector.reset()
        self.range.reset()

    def update(
        self,
        nis: float,
        innovation: NDArray[np.float64],
        innovation_std: NDArray[np.float64],
        current_residual: float,
        voltage_v: float,
        current_a: float,
        temperature_c: float,
    ) -> PassiveResult:
        """Advance all passive detectors using one EKF and sensor sample."""
        if innovation.shape != (2,) or innovation_std.shape != (2,):
            raise ValueError("voltage/temperature innovation vectors must have shape (2,)")
        if not np.all(np.isfinite(innovation_std)) or np.any(innovation_std <= 0):
            raise ValueError("innovation standard deviations must be finite and positive")
        z = {
            "V": float(innovation[0] / innovation_std[0]),
            "T": float(innovation[1] / innovation_std[1]),
            "I": float(current_residual / self.config.sensors.I_residual_sigma),
        }
        alarms: set[str] = set()
        nis_result = self.nis.update(nis)
        if nis_result.alarm:
            alarms.add("NIS")
        for channel, residual_z in z.items():
            if self.cusum[channel].update(residual_z).alarm:
                alarms.add(f"CUSUM_{channel}")
        alarms.update(
            f"RANGE_{channel}"
            for channel in self.range.check(voltage_v, current_a, temperature_c)
        )
        return {
            "alarms": alarms,
            "z": z,
            "nis_window_sum": nis_result.statistic,
        }
