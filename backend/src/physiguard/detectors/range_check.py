"""Static telemetry and temperature-rate plausibility checks (B0 baseline)."""

from __future__ import annotations

import math
from collections import deque

from ..config import Config, get_config


class RangeCheck:
    """Check voltage, current, temperature, and smoothed temperature rate."""

    def __init__(self, config: Config | None = None, rate_window_s: float = 5.0) -> None:
        self.config = config or get_config()
        if not math.isfinite(rate_window_s) or rate_window_s <= 0:
            raise ValueError("rate_window_s must be finite and positive")
        self.rate_window_s = rate_window_s
        self.time_s = 0.0
        max_points = math.ceil(rate_window_s / self.config.simulation.dt) + 1
        self.temperature_history: deque[tuple[float, float]] = deque(maxlen=max_points)

    def reset(self) -> None:
        """Clear the temperature-rate history and restart its clock."""
        self.time_s = 0.0
        self.temperature_history.clear()

    def check(self, voltage_v: float, current_a: float, temperature_c: float) -> set[str]:
        """Return channel names outside static limits or the thermal-rate limit."""
        p = self.config.plant
        dt_s = self.config.simulation.dt
        self.time_s += dt_s
        alarms: set[str] = set()
        if not math.isfinite(voltage_v) or not (p.V_min - 0.5 <= voltage_v <= p.V_hazard):
            alarms.add("V")
        if not math.isfinite(current_a) or not (-5.0 <= current_a <= p.I_rated + 5.0):
            alarms.add("I")
        if not math.isfinite(temperature_c) or not (p.T_amb - 20.0 <= temperature_c <= p.T_hazard):
            alarms.add("T")

        if math.isfinite(temperature_c):
            self.temperature_history.append((self.time_s, temperature_c))
            if len(self.temperature_history) >= 2:
                first_time, first_temp = self.temperature_history[0]
                elapsed = self.time_s - first_time
                if elapsed >= self.rate_window_s:
                    rate = abs(temperature_c - first_temp) / elapsed
                    if rate > self.config.detection.dTdt_limit:
                        alarms.add("dTdt")
        return alarms
