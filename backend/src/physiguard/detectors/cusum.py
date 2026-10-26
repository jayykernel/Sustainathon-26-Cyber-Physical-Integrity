"""Two-sided cumulative sum detector for standardized residual streams."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CUSUMResult:
    """CUSUM scores and alarm state after one residual sample."""

    positive: float
    negative: float
    alarm: bool


class CUSUM:
    """Detect sustained positive or negative standardized residual drift."""

    def __init__(self, kappa: float, threshold: float, deadband: float = 0.0) -> None:
        if not math.isfinite(kappa) or kappa <= 0:
            raise ValueError("kappa must be finite and positive")
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError("threshold must be finite and positive")
        if not math.isfinite(deadband) or deadband < 0:
            raise ValueError("deadband must be finite and non-negative")
        self.kappa = kappa
        self.threshold = threshold
        self.deadband = deadband
        self.positive = 0.0
        self.negative = 0.0

    def reset(self) -> None:
        """Clear both one-sided accumulators."""
        self.positive = 0.0
        self.negative = 0.0

    def update(self, residual_z: float) -> CUSUMResult:
        """Update both one-sided sums; reset after each alarm episode."""
        if not math.isfinite(residual_z):
            raise ValueError("standardized residual must be finite")
        magnitude = max(abs(residual_z) - self.deadband, 0.0)
        effective = math.copysign(magnitude, residual_z)
        self.positive = max(0.0, self.positive + effective - self.kappa)
        self.negative = max(0.0, self.negative - effective - self.kappa)
        alarm = max(self.positive, self.negative) > self.threshold
        if alarm:
            self.reset()
        return CUSUMResult(self.positive, self.negative, alarm)
