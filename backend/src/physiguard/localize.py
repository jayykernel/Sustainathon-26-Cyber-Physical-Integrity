"""Per-channel fault localization using full and cross-prediction EKFs."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

import numpy as np
import yaml

from .config import CONFIG_DIR, Config, get_config
from .twin import EKF, twin_ocv_lookup

LocalizedChannel = Literal["v", "i", "temp", "multi", "command", "unknown", "none"]


class LocalizationOutput(TypedDict):
    """One per-sample localization result and its auditable scores."""

    channel: LocalizedChannel
    confidence: float
    evidence: dict[str, float]


@dataclass(frozen=True)
class LocalizationConfig:
    """Window and decision settings calibrated on attack-free validation runs."""

    window_s: float = 60.0
    score_threshold: float = 2.0
    dominance_ratio: float = 1.5

    def __post_init__(self) -> None:
        if not np.isfinite(self.window_s) or self.window_s <= 0:
            raise ValueError("window_s must be finite and positive")
        if not np.isfinite(self.score_threshold) or self.score_threshold <= 0:
            raise ValueError("score_threshold must be finite and positive")
        if not np.isfinite(self.dominance_ratio) or self.dominance_ratio <= 1:
            raise ValueError("dominance_ratio must be finite and greater than one")


def load_localization_config(path: Path | str | None = None) -> LocalizationConfig:
    """Load validated localization settings from the project configuration."""
    config_path = Path(path) if path is not None else CONFIG_DIR / "localization.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Localization config not found: {config_path}")
    with config_path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError("localization config must contain a YAML mapping")
    return LocalizationConfig(**data)


def classify_scores(
    scores: dict[str, float],
    alarm: bool,
    settings: LocalizationConfig | None = None,
    command_tampered: bool = False,
) -> LocalizationOutput:
    """Apply the configured threshold and dominance rules to channel evidence."""
    cfg = settings or LocalizationConfig()
    if command_tampered:
        return {"channel": "command", "confidence": 1.0, "evidence": dict(scores)}
    evidence = {key: float(value) for key, value in scores.items()}
    if not alarm:
        return {"channel": "none", "confidence": 0.0, "evidence": evidence}
    candidates = sorted(
        ((key, value) for key, value in evidence.items() if value >= cfg.score_threshold),
        key=lambda item: item[1],
        reverse=True,
    )
    if not candidates:
        return {"channel": "unknown", "confidence": 0.0, "evidence": evidence}
    channel_names: dict[str, LocalizedChannel] = {"V": "v", "I": "i", "T": "temp"}
    top_name, top_score = candidates[0]
    if len(candidates) > 1:
        second_score = candidates[1][1]
        ratio = top_score / max(second_score, np.finfo(np.float64).tiny)
        if ratio < cfg.dominance_ratio:
            return {
                "channel": "multi",
                "confidence": float(min(1.0, len(candidates) / 3.0)),
                "evidence": evidence,
            }
        confidence = float(min(1.0, ratio / (ratio + cfg.dominance_ratio)))
    else:
        confidence = float(min(1.0, top_score / (top_score + cfg.score_threshold)))
    return {
        "channel": channel_names[top_name],
        "confidence": confidence,
        "evidence": evidence,
    }


class LocalizationEngine:
    """Maintain full, V-only, and T-only EKFs for 60-second cross-residuals."""

    def __init__(
        self,
        config: Config | None = None,
        settings: LocalizationConfig | None = None,
    ) -> None:
        self.config = config or get_config()
        self.settings = settings or load_localization_config()
        dt_s = float(self.config.simulation.dt)
        self.window_samples = max(1, int(np.ceil(self.settings.window_s / dt_s)))
        self.full_ekf = EKF(self.config)
        self.v_only_ekf = EKF(self.config)
        self.t_only_ekf = EKF(self.config)
        self.residuals: dict[str, deque[float]] = {
            name: deque(maxlen=self.window_samples)
            for name in ("V", "T", "I", "V_cross", "T_cross")
        }
        self.residual_sums_sq = dict.fromkeys(self.residuals, 0.0)
        self.initialized = False

    def reset(self) -> None:
        """Clear all filter and rolling-window state between runs."""
        self.full_ekf = EKF(self.config)
        self.v_only_ekf = EKF(self.config)
        self.t_only_ekf = EKF(self.config)
        for residuals in self.residuals.values():
            residuals.clear()
        self.residual_sums_sq = dict.fromkeys(self.residuals, 0.0)
        self.initialized = False

    def update(
        self,
        V_rep: float,
        I_rep: float,
        T_rep: float,
        I_cmd: float,
        alarm: bool,
        command_tampered: bool = False,
    ) -> LocalizationOutput:
        """Update the EKF bank and classify current channel evidence."""
        values = np.asarray([V_rep, I_rep, T_rep, I_cmd], dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError("localization inputs must be finite")
        if not self.initialized:
            self.full_ekf.initialize(V_rep, T_rep)
            self.v_only_ekf.initialize(V_rep, T_rep)
            self.t_only_ekf.initialize(V_rep, T_rep)
            self.initialized = True
            return classify_scores({}, alarm, self.settings, command_tampered)

        for ekf in (self.full_ekf, self.v_only_ekf, self.t_only_ekf):
            ekf.predict(I_cmd)

        full_result = self.full_ekf.update(V_rep, T_rep, I_cmd, I_meas=I_rep)
        z_v = float(full_result["nu"][0] / full_result["innovation_std"][0])
        z_t = float(full_result["nu"][1] / full_result["innovation_std"][1])
        z_i = float(full_result["r_I"] / self.config.sensors.I_residual_sigma)

        # Each reduced EKF predicts the channel it does not observe.
        t_variance = float(self.v_only_ekf.P[2, 2] + self.v_only_ekf.R[1, 1])
        t_cross = (T_rep - float(self.v_only_ekf.x[2])) / np.sqrt(t_variance)

        x_v = float(self.t_only_ekf.x[0])
        x_v1 = float(self.t_only_ekf.x[1])
        p = self.config.twin
        predicted_v = twin_ocv_lookup(x_v, self.config) + I_cmd * p.R0_n + x_v1
        h_v = np.array([self.t_only_ekf._d_ocv_d_soc(x_v), 1.0, 0.0], dtype=np.float64)
        v_variance = float(h_v @ self.t_only_ekf.P @ h_v.T + self.t_only_ekf.R[0, 0])
        v_cross = (V_rep - predicted_v) / np.sqrt(v_variance)

        self.v_only_ekf.update_channel("V", V_rep, I_cmd)
        self.t_only_ekf.update_channel("T", T_rep, I_cmd)
        for name, residual in (
            ("V", z_v),
            ("T", z_t),
            ("I", z_i),
            ("V_cross", float(v_cross)),
            ("T_cross", float(t_cross)),
        ):
            self._append_residual(name, residual)

        scores = {
            "V": self._window_rms("V", "V_cross"),
            "T": self._window_rms("T", "T_cross"),
            "I": self._window_rms("I"),
        }
        return classify_scores(scores, alarm, self.settings, command_tampered)

    def _append_residual(self, name: str, residual: float) -> None:
        """Update the bounded window and its sum of squares in constant time."""
        values = self.residuals[name]
        if len(values) == values.maxlen:
            oldest = values[0]
            self.residual_sums_sq[name] -= oldest * oldest
        values.append(residual)
        self.residual_sums_sq[name] += residual * residual

    def _window_rms(self, *names: str) -> float:
        count = sum(len(self.residuals[name]) for name in names)
        if count == 0:
            return 0.0
        sum_squares = max(0.0, sum(self.residual_sums_sq[name] for name in names))
        return float(np.sqrt(sum_squares / count))

    @staticmethod
    def _rms(*series: deque[float]) -> float:
        values = np.concatenate([np.asarray(item, dtype=np.float64) for item in series])
        if values.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(values))))
