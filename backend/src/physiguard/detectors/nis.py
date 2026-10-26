"""Sliding-window normalized innovation squared detector."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class NISResult:
    """Window statistic and current alarm state."""

    statistic: float | None
    alarm: bool


class NISWindow:
    """Alarm when the sum of the latest `window_size` NIS values exceeds a limit."""

    def __init__(self, window_size: int, threshold: float) -> None:
        if window_size < 1:
            raise ValueError("window_size must be positive")
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError("threshold must be finite and positive")
        self.window_size = window_size
        self.threshold = threshold
        self.values: deque[float] = deque(maxlen=window_size)

    def reset(self) -> None:
        """Clear accumulated NIS samples."""
        self.values.clear()

    def update(self, nis: float) -> NISResult:
        """Add one finite non-negative NIS value and return the rolling sum."""
        if not math.isfinite(nis) or nis < 0:
            raise ValueError("NIS must be finite and non-negative")
        self.values.append(nis)
        if len(self.values) < self.window_size:
            return NISResult(None, False)
        statistic = math.fsum(self.values)
        return NISResult(statistic, statistic > self.threshold)
