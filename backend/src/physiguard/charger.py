"""Upstream CC/CV profile and charger-side reported-temperature derating."""

from __future__ import annotations

from .config import Config, get_config


def profile_request(voltage_v: float, config: Config | None = None) -> float:
    """Request fast current below Vmax, then taper linearly in constant voltage."""
    c = (config or get_config()).charger
    if voltage_v < c.V_max:
        return c.I_fast
    return max(0.0, c.CV_kp * (c.V_max - voltage_v))


class ChargeProfile:
    """Stateful CC/CV profile that stays in CV after first reaching the limit."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self.in_cv_phase = False

    def request(self, voltage_v: float) -> float:
        """Return the requested current and latch CV mode at the voltage limit."""
        c = self.config.charger
        if voltage_v >= c.V_max:
            self.in_cv_phase = True
        if not self.in_cv_phase:
            return c.I_fast
        return max(0.0, c.CV_kp * (c.V_max - voltage_v))


def thermal_derate_factor(temperature_reported_c: float, config: Config | None = None) -> float:
    """Compute the charger's linear derating from the reported temperature."""
    c = (config or get_config()).charger
    if temperature_reported_c <= c.T_derate_start:
        return 1.0
    if temperature_reported_c >= c.T_derate_end:
        return c.derate_min_factor
    progress = (temperature_reported_c - c.T_derate_start) / (
        c.T_derate_end - c.T_derate_start
    )
    return 1.0 - progress * (1.0 - c.derate_min_factor)


def execute_request(
    requested_current_a: float,
    temperature_reported_c: float,
    config: Config | None = None,
) -> float:
    """Apply the rated-current cap and reported-temperature thermal derate."""
    c = (config or get_config()).charger
    bounded_request = min(max(requested_current_a, 0.0), c.I_rated)
    return bounded_request * thermal_derate_factor(temperature_reported_c, config)
