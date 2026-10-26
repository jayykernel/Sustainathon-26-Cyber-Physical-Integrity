"""Hysteretic incident response and trust-aware virtual sensing."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from .config import Config, get_config
from .twin import EKF, Twin

ResponseState = Literal["NORMAL", "SUSPECT", "CONFIRMED", "SAFE_MODE"]
EstimateQuality = Literal["normal", "degraded"]


class ResponseEvent(TypedDict):
    """Auditable response event for UI and report consumers."""

    time_s: float
    severity: Literal["info", "warning", "critical"]
    code: str
    text: str


@dataclass(frozen=True)
class ResponseSnapshot:
    """State-machine outputs for a single simulation step."""

    state: ResponseState
    continuous_probe: bool
    use_virtual_temperature: bool
    safe_mode: bool
    confirmed: bool


class ResponseManager:
    """Apply independent-evidence confirmation, persistence, and reset hysteresis."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self.state: ResponseState = "NORMAL"
        self._evidence: deque[tuple[float, str]] = deque()
        self._probe_failures = 0
        self._confirmed_since: float | None = None
        self._clean_windows = 0
        self._reset_requested = False
        self._events: list[ResponseEvent] = []

    @property
    def events(self) -> list[ResponseEvent]:
        return list(self._events)

    def update(
        self,
        time_s: float,
        evidence_classes: set[str] | frozenset[str] = frozenset(),
        *,
        probe_failed: bool = False,
        command_unsafe: bool = False,
        prediction_violation: bool = False,
        clean_challenge: bool = False,
    ) -> ResponseSnapshot:
        """Ingest evidence and advance the state machine without oscillation."""
        if not np.isfinite(time_s) or time_s < 0:
            raise ValueError("time_s must be finite and non-negative")
        classes = set(evidence_classes)
        if command_unsafe:
            classes.add("command_unsafe")
        if self.state in {"NORMAL", "SUSPECT"} and classes:
            if self.state == "NORMAL":
                self.state = "SUSPECT"
                self._emit(time_s, "warning", "suspect", "Integrity evidence detected.")
            for evidence in classes:
                self._evidence.append((float(time_s), evidence))
            self._expire_evidence(time_s)
            distinct = {kind for _, kind in self._evidence}
            direct_confirmation = command_unsafe and prediction_violation
            if (
                len(distinct) >= int(self.config.response.SUSPECT_to_CONFIRMED_evidence_classes)
                or direct_confirmation
            ):
                self._confirm(time_s)
        elif self.state == "SUSPECT":
            self._expire_evidence(time_s)

        if probe_failed:
            self._probe_failures += 1
            if self._probe_failures == 1 and self.state == "NORMAL":
                self.state = "SUSPECT"
                self._emit(time_s, "warning", "suspect", "Probe verification failed.")
            if self._probe_failures >= 2 and self.state in {"NORMAL", "SUSPECT"}:
                self._confirm(time_s, "Two consecutive probe windows failed verification.")
        elif clean_challenge:
            self._probe_failures = 0

        if self.state == "CONFIRMED":
            assert self._confirmed_since is not None
            if time_s - self._confirmed_since >= float(
                self.config.response.CONFIRMED_to_SAFE_MODE_persist
            ):
                self.state = "SAFE_MODE"
                self._clean_windows = 0
                self._emit(time_s, "critical", "safe_mode", "Safe charging mode engaged.")

        if self.state == "SAFE_MODE" and clean_challenge:
            self._clean_windows += 1
        elif self.state == "SAFE_MODE" and not clean_challenge:
            self._clean_windows = 0

        if (
            self.state == "SAFE_MODE"
            and self._reset_requested
            and self._clean_windows >= int(self.config.response.N_clean)
        ):
            self.state = "NORMAL"
            self._reset_requested = False
            self._evidence.clear()
            self._confirmed_since = None
            self._emit(time_s, "info", "operator_reset", "Operator reset accepted after clean checks.")

        return ResponseSnapshot(
            state=self.state,
            continuous_probe=self.state in {"SUSPECT", "CONFIRMED", "SAFE_MODE"},
            use_virtual_temperature=self.state == "SAFE_MODE",
            safe_mode=self.state == "SAFE_MODE",
            confirmed=self.state in {"CONFIRMED", "SAFE_MODE"},
        )

    def request_operator_reset(self, time_s: float) -> bool:
        """Record an explicit reset request; NORMAL requires N_clean first."""
        if self.state != "SAFE_MODE":
            return False
        self._reset_requested = True
        self._emit(time_s, "info", "reset_requested", "Operator requested reset.")
        return True

    def _expire_evidence(self, time_s: float) -> None:
        cutoff = time_s - float(self.config.response.SUSPECT_to_CONFIRMED_window)
        while self._evidence and self._evidence[0][0] < cutoff:
            self._evidence.popleft()

    def _confirm(self, time_s: float, text: str = "Independent integrity evidence confirmed.") -> None:
        if self.state in {"CONFIRMED", "SAFE_MODE"}:
            return
        self.state = "CONFIRMED"
        self._confirmed_since = float(time_s)
        self._emit(time_s, "critical", "confirmed", text)

    def _emit(
        self,
        time_s: float,
        severity: Literal["info", "warning", "critical"],
        code: str,
        text: str,
    ) -> None:
        self._events.append(
            {"time_s": float(time_s), "severity": severity, "code": code, "text": text}
        )


class VirtualSensor:
    """Estimate SOC, polarization, and temperature using only trusted channels."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self.ekf = EKF(self.config)
        pessimistic = deepcopy(self.config)
        pessimistic.twin.R_th_n *= float(self.config.command_guard.R_th_worst)
        pessimistic.twin.R0_n *= float(self.config.command_guard.R0_pessimism)
        pessimistic.twin.T_amb_hat += float(self.config.command_guard.T_amb_pessimism)
        self.open_loop = Twin(pessimistic)
        self.initialized = False
        self.quality: EstimateQuality = "normal"

    @property
    def state(self) -> NDArray[np.float64]:
        """Return current [SOC, V1, temperature] estimate."""
        if not self.initialized:
            if self.ekf.initialized:
                return self.ekf.x.copy()
            assert self.open_loop.x is not None
            return self.open_loop.x.copy()
        if self.quality == "degraded":
            assert self.open_loop.x is not None
            return self.open_loop.x.copy()
        return self.ekf.x.copy()

    def update(
        self,
        V_rep: float,
        T_rep: float,
        I_cmd: float,
        flagged_channels: set[str] | frozenset[str] = frozenset(),
        *,
        force_degraded: bool = False,
    ) -> tuple[float, EstimateQuality]:
        """Advance estimate and fuse unflagged voltage and temperature evidence."""
        flagged = {channel.upper() for channel in flagged_channels}
        if not self.initialized:
            self.ekf.initialize(V_rep, T_rep)
            self.open_loop.x = self.ekf.x.copy()
            self.initialized = True
        else:
            self.ekf.predict(I_cmd)
            self.open_loop.step(I_cmd)

        trusted = {channel for channel in ("V", "T") if channel not in flagged}
        if force_degraded or not trusted:
            self.quality = "degraded"
            return float(self.open_loop.x[2]), self.quality  # type: ignore[index]

        self.quality = "normal"
        if "V" in trusted:
            self.ekf.update_channel("V", V_rep, I_cmd)
        if "T" in trusted:
            self.ekf.update_channel("T", T_rep, I_cmd)
        self.open_loop.x = self.ekf.x.copy()
        return float(self.ekf.x[2]), self.quality
