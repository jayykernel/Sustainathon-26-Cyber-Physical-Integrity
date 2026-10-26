"""Keyed, balanced PRBS charge probes with current, voltage, and thermal bounds."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..config import Config, get_config
from ..plant import Plant, ocv_lookup, plant_step, resistance_r0

_PROCESS_KEY = secrets.token_bytes(32)


@dataclass(frozen=True)
class ProbeWindow:
    """One deterministic challenge window and its nonce."""

    delta_I: NDArray[np.float64]
    nonce: bytes
    amplitude_a: float


def _key_bytes(key: bytes | str | None, config: Config) -> bytes:
    if key is None:
        configured = config.probe.key
        return configured.encode("utf-8") if configured else _PROCESS_KEY
    return key.encode("utf-8") if isinstance(key, str) else bytes(key)


def _safe_at_amplitude(
    amplitude_a: float,
    base_current_a: float,
    plant: Plant,
    config: Config,
) -> bool:
    p = config.plant
    if base_current_a - amplitude_a < -1e-12 or base_current_a + amplitude_a > p.I_rated + 1e-12:
        return False
    for current_a in (base_current_a - amplitude_a, base_current_a + amplitude_a):
        soc, v1, v2, temperature = plant_step(
            plant.soc,
            plant.v1,
            plant.v2,
            plant.temperature_c,
            current_a,
            config,
        )
        voltage = (
            float(ocv_lookup(soc, p.OCV_offset))
            + current_a * resistance_r0(config, temperature)
            + v1
            + v2
        )
        if voltage > p.V_max or temperature > p.T_warn:
            return False
    return True


def is_probe_current_safe(current_a: float, plant: Plant, config: Config) -> bool:
    """Check the next plant step against rated-current, voltage, and thermal limits."""
    return _safe_at_amplitude(0.0, current_a, plant, config)


def _clip_symmetric_amplitude(
    requested_a: float,
    base_current_a: float,
    plant: Plant | None,
    config: Config,
) -> float:
    maximum = min(requested_a, max(0.0, base_current_a), max(0.0, config.plant.I_rated - base_current_a))
    if plant is None:
        return maximum
    if _safe_at_amplitude(maximum, base_current_a, plant, config):
        return maximum
    lower, upper = 0.0, maximum
    for _ in range(24):
        midpoint = 0.5 * (lower + upper)
        if _safe_at_amplitude(midpoint, base_current_a, plant, config):
            lower = midpoint
        else:
            upper = midpoint
    return lower


def generate_probe_window(
    base_current_a: float,
    amplitude_reference_a: float,
    sample_count: int,
    key: bytes | str | None = None,
    nonce: bytes | None = None,
    config: Config | None = None,
    plant: Plant | None = None,
    amplitude_pct: float | None = None,
) -> ProbeWindow:
    """Generate balanced ±a chips from an HMAC-derived PCG64 seed.

    The probe has an exact zero mean. When a plant state is supplied, its common
    amplitude is binary-searched so both signs stay below V_max and T_warn.
    """
    cfg = config or get_config()
    values = np.asarray([base_current_a, amplitude_reference_a], dtype=np.float64)
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("current and amplitude reference must be finite and non-negative")
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    chip_length = int(cfg.probe.chip_length)
    if sample_count % chip_length != 0 or (sample_count // chip_length) % 2:
        raise ValueError("sample_count must contain an even number of complete chips")

    challenge_nonce = nonce if nonce is not None else secrets.token_bytes(16)
    if not challenge_nonce:
        raise ValueError("nonce must not be empty")
    secret = _key_bytes(key, cfg)
    seed_digest = hmac.new(secret, challenge_nonce, hashlib.sha256).digest()
    seed = int.from_bytes(seed_digest[:16], "big")
    rng = np.random.Generator(np.random.PCG64(seed))

    selected_pct = cfg.probe.amplitude_pct if amplitude_pct is None else amplitude_pct
    if not np.isfinite(selected_pct) or not 0.0 <= selected_pct <= 20.0:
        raise ValueError("amplitude_pct must be finite and in [0, 20]")
    requested_amplitude = amplitude_reference_a * selected_pct / 100.0
    amplitude = _clip_symmetric_amplitude(requested_amplitude, base_current_a, plant, cfg)
    chip_count = sample_count // chip_length
    signs = np.concatenate(
        (np.ones(chip_count // 2, dtype=np.float64), -np.ones(chip_count // 2, dtype=np.float64))
    )
    rng.shuffle(signs)
    delta = np.repeat(signs, chip_length) * amplitude
    delta.setflags(write=False)
    return ProbeWindow(delta_I=delta, nonce=challenge_nonce, amplitude_a=amplitude)


class ProbeScheduler:
    """Schedule periodic NORMAL windows and fresh windows in continuous modes."""

    def __init__(self, config: Config | None = None, seed: int = 0) -> None:
        self.config = config or get_config()
        self.rng = np.random.default_rng(seed)
        self._nonces: dict[tuple[str, int], bytes] = {}

    def window_index(self, time_s: float, mode: str = "NORMAL") -> int:
        if mode.upper() in self.config.probe.continuous_modes:
            return int(time_s // self.config.probe.window)
        return int(time_s // self.config.probe.period)

    def is_active(self, time_s: float, mode: str = "NORMAL") -> bool:
        if time_s < 0:
            return False
        if mode.upper() in self.config.probe.continuous_modes:
            return True
        return time_s % self.config.probe.period < self.config.probe.window

    def nonce_for(self, time_s: float, mode: str = "NORMAL") -> bytes | None:
        """Return one stable nonce per active challenge window."""
        if not self.is_active(time_s, mode):
            return None
        index = self.window_index(time_s, mode)
        key = (mode.upper(), index)
        if key not in self._nonces:
            self._nonces[key] = self.rng.bytes(16)
        return self._nonces[key]
