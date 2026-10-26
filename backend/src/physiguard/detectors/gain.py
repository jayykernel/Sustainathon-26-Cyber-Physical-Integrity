"""High-pass regression tests for the voltage and current probe response."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from numpy.typing import ArrayLike, NDArray

from ..config import CONFIG_DIR, Config, get_config
from ..twin import twin_ocv_lookup


@dataclass(frozen=True)
class GainEstimate:
    """Least-squares probe gain and its noise-derived standard error."""

    gain: float
    standard_error: float
    denominator: float
    samples: int


@dataclass(frozen=True)
class GainDecision:
    """Separate voltage, current, and combined active-test decisions."""

    voltage: GainEstimate
    current: GainEstimate
    detected_voltage: bool
    detected_current: bool
    detected_combined: bool


def load_gain_thresholds(
    config: Config | None = None, path: Path | str | None = None
) -> tuple[float, float]:
    """Load P5 validation thresholds, checking the config hash when available."""
    cfg = config or get_config()
    calibration_path = Path(path) if path is not None else CONFIG_DIR / "probe_calibration.yaml"
    if not calibration_path.exists():
        return cfg.probe.g_min_V, cfg.probe.g_min_I
    with calibration_path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError("probe calibration must be a YAML mapping")
    source_hash = data.get("config_hash")
    if source_hash and source_hash != cfg.config_hash():
        raise ValueError("probe gain thresholds were calibrated for a different config hash")
    g_min_v = float(data.get("g_min_V", cfg.probe.g_min_V))
    g_min_i = float(data.get("g_min_I", cfg.probe.g_min_I))
    if not (np.isfinite(g_min_v) and 0.0 < g_min_v <= 1.0):
        raise ValueError("calibrated g_min_V must be in (0, 1]")
    if not (np.isfinite(g_min_i) and 0.0 < g_min_i <= 1.0):
        raise ValueError("calibrated g_min_I must be in (0, 1]")
    return g_min_v, g_min_i


def _high_pass(values: NDArray[np.float64], window_samples: int) -> NDArray[np.float64]:
    width = min(max(1, window_samples), values.size)
    left = width // 2
    right = width - 1 - left
    padded = np.pad(values, (left, right), mode="edge")
    average = np.convolve(padded, np.full(width, 1.0 / width), mode="valid")
    return values - average


def expected_voltage_response(
    delta_I: ArrayLike,
    config: Config | None = None,
    initial_soc: float | None = None,
) -> NDArray[np.float64]:
    """Compute the twin's small-signal V response to a current probe sequence."""
    cfg = config or get_config()
    current_delta = np.asarray(delta_I, dtype=np.float64)
    if current_delta.ndim != 1 or not np.all(np.isfinite(current_delta)):
        raise ValueError("delta_I must be a finite one-dimensional sequence")
    soc = float(cfg.plant.SOC_0 if initial_soc is None else initial_soc)
    soc_delta = 0.0
    v1_delta = 0.0
    dt_s = float(cfg.simulation.dt)
    p = cfg.twin
    decay = np.exp(-dt_s / p.tau1_n)
    output = np.empty_like(current_delta)
    for index, current in enumerate(current_delta):
        soc += cfg.plant.eta * current * dt_s / (3600.0 * p.Q_n)
        soc_delta += cfg.plant.eta * current * dt_s / (3600.0 * p.Q_n)
        v1_delta = v1_delta * decay + p.R1_n * (1.0 - decay) * current
        step = 1e-4
        low = max(0.0, soc - step)
        high = min(1.0, soc + step)
        slope = (
            (twin_ocv_lookup(high, cfg) - twin_ocv_lookup(low, cfg)) / (high - low)
            if high > low
            else 0.0
        )
        output[index] = slope * soc_delta + p.R0_n * current + v1_delta
    return output


def estimate_gain(
    observed: ArrayLike,
    expected: ArrayLike,
    noise_sigma: float,
    high_pass_window_s: float = 60.0,
    config: Config | None = None,
) -> GainEstimate:
    """Estimate gain after subtracting a moving-average baseline."""
    cfg = config or get_config()
    y = np.asarray(observed, dtype=np.float64)
    s = np.asarray(expected, dtype=np.float64)
    if y.ndim != 1 or s.ndim != 1 or y.shape != s.shape or y.size < 2:
        raise ValueError("observed and expected must be equal-length one-dimensional arrays")
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(s)):
        raise ValueError("observed and expected sequences must be finite")
    if not np.isfinite(noise_sigma) or noise_sigma <= 0:
        raise ValueError("noise_sigma must be finite and positive")
    if not np.isfinite(high_pass_window_s) or high_pass_window_s <= 0:
        raise ValueError("high_pass_window_s must be finite and positive")
    window_samples = max(1, int(round(high_pass_window_s / cfg.simulation.dt)))
    y_hp = _high_pass(y, window_samples)
    s_hp = _high_pass(s, window_samples)
    denominator = float(s_hp @ s_hp)
    if denominator <= np.finfo(np.float64).eps:
        raise ValueError("expected probe response has insufficient high-pass energy")
    gain = float((y_hp @ s_hp) / denominator)
    standard_error = float(noise_sigma / np.sqrt(denominator))
    return GainEstimate(gain, standard_error, denominator, int(y.size))


def evaluate_gain_window(
    voltage_reported: ArrayLike,
    current_reported: ArrayLike,
    delta_I: ArrayLike,
    config: Config | None = None,
    g_min_v: float | None = None,
    g_min_i: float | None = None,
    initial_soc: float | None = None,
) -> GainDecision:
    """Evaluate V-only, I-only, and OR-combined gain alarms for one challenge."""
    cfg = config or get_config()
    if g_min_v is None or g_min_i is None:
        calibrated_v, calibrated_i = load_gain_thresholds(cfg)
    else:
        calibrated_v, calibrated_i = g_min_v, g_min_i
    v_threshold = calibrated_v if g_min_v is None else g_min_v
    i_threshold = calibrated_i if g_min_i is None else g_min_i
    voltage_expected = expected_voltage_response(delta_I, cfg, initial_soc=initial_soc)
    current_expected = np.asarray(delta_I, dtype=np.float64)
    voltage = estimate_gain(
        voltage_reported, voltage_expected, cfg.sensors.V_sigma, config=cfg
    )
    current = estimate_gain(
        current_reported, current_expected, cfg.sensors.I_sigma, config=cfg
    )
    detected_v = voltage.gain < v_threshold
    detected_i = current.gain < i_threshold
    return GainDecision(voltage, current, detected_v, detected_i, detected_v or detected_i)
