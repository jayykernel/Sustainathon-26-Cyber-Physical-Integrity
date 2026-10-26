"""Configuration system for PhysiGuard.

Single source of truth for all parameters. Loads from YAML, validates with pydantic,
provides config hash for reproducibility.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOG_LEVEL = os.environ.get("PHYSIGUARD_LOG_LEVEL", "INFO").upper()


def setup_logging() -> None:
    """Configure JSON logging for the application."""
    import json
    import sys
    from datetime import UTC, datetime

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_data = {
                "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if hasattr(record, "session_id"):
                log_data["session_id"] = record.session_id
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_data)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(LOG_LEVEL)


# -----------------------------------------------------------------------------
# Pydantic models for configuration
# -----------------------------------------------------------------------------


class PlantConfig(BaseModel):
    """Plant (ground truth simulator) parameters."""

    Q: float = Field(60.0, gt=0, description="Capacity in Ah")
    R0_ref: float = Field(1.2e-3, gt=0, description="Ohmic resistance at 25°C in ohms")
    R1: float = Field(0.6e-3, gt=0, description="First RC resistance in ohms")
    tau1: float = Field(30.0, gt=0, description="First RC time constant in seconds")
    R2: float = Field(0.5e-3, gt=0, description="Second RC resistance in ohms")
    tau2: float = Field(160.0, gt=0, description="Second RC time constant in seconds")
    C_th: float = Field(800.0, gt=0, description="Thermal capacitance in J/K")
    R_th: float = Field(2.5, gt=0, description="Thermal resistance in K/W")
    T_amb: float = Field(35.0, description="Ambient temperature in °C")
    T_amb_drift_rate: float = Field(1.5 / 3600, description="Ambient drift rate in °C/s (±1.5°C/h)")
    SOC_0: float = Field(0.10, ge=0, le=1, description="Initial SOC")
    T_0: float | None = Field(None, description="Initial temperature (None = T_amb)")
    eta: float = Field(0.995, gt=0, le=1, description="Coulombic efficiency (charging)")
    a_R: float = Field(0.012, description="Temperature coefficient of R0 in 1/°C")
    # Variation (seeded per run)
    Q_var_pct: float = Field(3.0, ge=0, description="Capacity variation ±%")
    R0_var_pct: float = Field(10.0, ge=0, description="R0 variation ±%")
    R1_var_pct: float = Field(10.0, ge=0, description="R1 variation ±%")
    R_th_var_pct: float = Field(10.0, ge=0, description="R_th variation ±%")
    OCV_offset_mV: float = Field(10.0, ge=0, description="OCV table offset ±mV")
    # Limits
    T_hazard: float = Field(55.0, description="Thermal hazard temperature in °C")
    T_warn: float = Field(50.0, description="Warning temperature in °C")
    V_hazard: float = Field(4.30, description="Overvoltage hazard in V")
    V_max: float = Field(4.20, description="Maximum terminal voltage in V")
    V_min: float = Field(3.00, description="Minimum terminal voltage in V")
    I_rated: float = Field(180.0, gt=0, description="Rated current limit in A (3C)")

    @model_validator(mode="after")
    def validate_temp_ordering(self) -> PlantConfig:
        if not (self.T_warn < self.T_hazard):
            raise ValueError("T_warn must be < T_hazard")
        if not (self.V_min < self.V_max < self.V_hazard):
            raise ValueError("V_min < V_max < V_hazard required")
        return self


class TwinConfig(BaseModel):
    """Digital twin (1-RC) parameters."""

    Q_n: float = Field(60.0, gt=0, description="Nominal capacity in Ah")
    R0_n: float = Field(1.2e-3, gt=0, description="Nominal ohmic resistance in ohms")
    R1_n: float = Field(1.1e-3, gt=0, description="Lumped RC resistance in ohms (R1+R2)")
    tau1_n: float = Field(60.0, gt=0, description="Lumped RC time constant in seconds")
    C_th_n: float = Field(800.0, gt=0, description="Nominal thermal capacitance in J/K")
    R_th_n: float = Field(2.5, gt=0, description="Nominal thermal resistance in K/W")
    T_amb_hat: float = Field(35.0, description="Assumed ambient temperature in °C")
    # OCV table (SOC from 0.0 to 1.0 step 0.1)
    OCV_n: list[float] = Field(
        default_factory=lambda: [3.00, 3.30, 3.45, 3.55, 3.62, 3.68, 3.75, 3.82, 3.92, 4.05, 4.20],
        min_length=11,
        max_length=11,
    )


class SensorConfig(BaseModel):
    """Sensor noise and quantization parameters."""

    V_sigma: float = Field(0.008, gt=0, description="Voltage noise std in V")
    I_sigma: float = Field(0.15, gt=0, description="Current noise std in A")
    T_sigma: float = Field(0.10, gt=0, description="Temperature noise std in °C")
    V_quant: float = Field(0.001, gt=0, description="Voltage quantization in V (1 mV)")
    I_quant: float = Field(0.01, gt=0, description="Current quantization in A")
    T_quant: float = Field(0.01, gt=0, description="Temperature quantization in °C")
    # Current-consistency residual noise
    I_residual_sigma: float = Field(0.2, gt=0, description="Current residual noise std in A")


class ChargerConfig(BaseModel):
    """Charger/profile controller parameters."""

    I_fast: float = Field(90.0, gt=0, description="Fast charge current in A (1.5C)")
    I_rated: float = Field(180.0, gt=0, description="Hard current limit in A")
    V_max: float = Field(4.20, description="CV target voltage in V")
    # Thermal derating on reported temperature
    T_derate_start: float = Field(40.0, description="Derate start temp in °C")
    T_derate_end: float = Field(50.0, description="Derate end temp (min current) in °C")
    derate_min_factor: float = Field(0.2, ge=0, le=1, description="Minimum current factor at T_derate_end")
    # CV proportional controller
    CV_kp: float = Field(200.0, gt=0, description="CV proportional gain in A/V")


class DetectionConfig(BaseModel):
    """Detection thresholds and parameters (written by calibration)."""

    FA_target: float = Field(0.2, gt=0, description="Target false alarms per simulated hour (combined)")
    # Window lengths
    NIS_window: int = Field(30, gt=0, description="NIS window length in seconds")
    CUSUM_kappa: float = Field(0.5, gt=0, description="CUSUM reference value")
    CUSUM_h: float = Field(6.0, gt=0, description="CUSUM threshold")
    CUSUM_deadband: float = Field(0.5, ge=0, description="CUSUM deadband (std units)")
    # Range limits
    dTdt_limit: float = Field(0.5, gt=0, description="Max temperature rate of change in °C/s")
    # Calibration metadata (populated by make calibrate)
    NIS_threshold: float = Field(11.0, gt=0, description="Calibrated NIS window threshold")
    calibration_seeds: list[int] = Field(default_factory=lambda: list(range(100)))
    calibration_config_hash: str = Field("", description="Config hash at calibration time")
    calibration_date: str = Field("", description="ISO date of calibration")


class ProbeConfig(BaseModel):
    """Active verification probe parameters."""

    amplitude_pct: float = Field(4.0, gt=0, le=20, description="Probe amplitude as % of I_req")
    chip_length: int = Field(5, gt=0, description="PRBS chip length in seconds")
    window: int = Field(120, gt=0, description="Challenge window length in seconds")
    period: int = Field(600, gt=0, description="Challenge period in seconds (NORMAL mode)")
    continuous_modes: list[str] = Field(
        default_factory=lambda: ["SUSPECT", "CONFIRMED", "SAFE_MODE"],
        description="Modes with continuous probing",
    )
    # Gain test calibration
    g_min_V: float = Field(0.5, gt=0, le=1, description="Minimum voltage gain for authentic telemetry")
    g_min_I: float = Field(0.5, gt=0, le=1, description="Minimum current gain for authentic telemetry")
    # Probe key (from env, fallback for demos)
    key: str = Field("", description="HMAC key for probe PRNG (from env)")
    # Amplitude sweep parameters
    sweep_amplitudes: list[float] = Field(
        default_factory=lambda: [0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        description="Probe amplitude sweep values (% of I_req)",
    )
    sweep_modes: list[str] = Field(
        default_factory=lambda: ["passive_with_probe", "gain_test"],
        description="Modes for sweep experiment",
    )


class LocalizationConfig(BaseModel):
    """Channel localization parameters."""

    window: int = Field(60, gt=0, description="Localization window in seconds")
    dominance_factor: float = Field(1.5, gt=1, description="Dominance factor for channel blame")


class CommandGuardConfig(BaseModel):
    """Command guard parameters."""

    horizon: int = Field(300, gt=0, description="Forward simulation horizon in seconds")
    R_th_pessimism: float = Field(1.5, gt=1, description="Pessimistic R_th multiplier")
    T_amb_pessimism: float = Field(5.0, gt=0, description="Pessimistic T_amb increase in °C")
    R0_pessimism: float = Field(1.2, gt=1, description="Pessimistic R0 multiplier")
    bisection_max_iter: int = Field(8, gt=0, le=20, description="Max bisection iterations")
    # SAFE_MODE worst-case
    R_th_worst: float = Field(4.0, gt=1, description="Worst-case R_th multiplier for SAFE_MODE")


class ResponseConfig(BaseModel):
    """Response state machine parameters."""

    N_clean: int = Field(3, gt=0, description="Clean windows required to exit SAFE_MODE")
    SUSPECT_to_CONFIRMED_evidence_classes: int = Field(2, gt=0, description="Independent evidence classes for CONFIRMED")
    SUSPECT_to_CONFIRMED_window: int = Field(60, gt=0, description="Time window for evidence accumulation in seconds")
    CONFIRMED_to_SAFE_MODE_persist: int = Field(10, gt=0, description="CONFIRMED persistence before SAFE_MODE in seconds")
    evidence_classes: list[str] = Field(
        default_factory=lambda: ["passive_NIS", "CUSUM", "probe_gain", "command_unsafe"],
        description="Evidence class names",
    )


class SimulationConfig(BaseModel):
    """Global simulation parameters."""

    dt: float = Field(1.0, gt=0, description="Time step in seconds")
    duration: int = Field(3600, gt=0, description="Simulation duration in seconds")
    seed: int | None = Field(None, description="Global seed (None = random per run)")


class Config(BaseModel):
    """Top-level configuration container."""

    plant: PlantConfig = Field(default_factory=lambda: PlantConfig())
    twin: TwinConfig = Field(default_factory=lambda: TwinConfig())
    sensors: SensorConfig = Field(default_factory=lambda: SensorConfig())
    charger: ChargerConfig = Field(default_factory=lambda: ChargerConfig())
    detection: DetectionConfig = Field(default_factory=lambda: DetectionConfig())
    probe: ProbeConfig = Field(default_factory=lambda: ProbeConfig())
    localization: LocalizationConfig = Field(default_factory=lambda: LocalizationConfig())
    command_guard: CommandGuardConfig = Field(default_factory=lambda: CommandGuardConfig())
    response: ResponseConfig = Field(default_factory=lambda: ResponseConfig())
    simulation: SimulationConfig = Field(default_factory=lambda: SimulationConfig())

    # Computed fields (not in YAML)
    _config_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        self._config_hash = self.config_hash()

    def config_hash(self) -> str:
        """Compute deterministic hash of the configuration (excluding computed fields)."""
        # Dump to YAML without the private field
        data = self.model_dump(exclude={"_config_hash"}, mode="json")
        yaml_str = yaml.dump(data, sort_keys=True, default_flow_style=False)
        return hashlib.sha256(yaml_str.encode()).hexdigest()[:16]

    @property
    def config_hash_short(self) -> str:
        return self._config_hash


# -----------------------------------------------------------------------------
# Loader
# -----------------------------------------------------------------------------

# CONFIG_DIR: the project root configs/ directory
def _find_config_dir() -> Path:
    """Find the configs directory at project root."""
    # Try relative to this file's source location (development)
    # config.py is at backend/src/physiguard/config.py
    # project root is backend/../../
    src_dir = Path(__file__).parent
    candidate = src_dir.parent.parent.parent / "configs"
    if candidate.exists():
        return candidate
    # Try relative to cwd (when running from project root)
    candidate = Path.cwd() / "configs"
    if candidate.exists():
        return candidate
    # Try cwd parent (when running from backend/)
    candidate = Path.cwd().parent / "configs"
    if candidate.exists():
        return candidate
    # Fallback: use source-relative (will fail with clear error if missing)
    return src_dir.parent.parent.parent / "configs"


CONFIG_DIR = _find_config_dir()


def load_config(path: Path | str | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        path: Path to YAML file. If None, uses configs/default.yaml.

    Returns:
        Validated Config object.
    """
    if path is None:
        path = CONFIG_DIR / "default.yaml"

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")

    # Environment variable override for probe key
    if "probe" in data and "key" in data["probe"]:
        env_key = os.environ.get("PHYSIGUARD_PROBE_KEY")
        if env_key:
            data["probe"]["key"] = env_key

    config = Config(**data)
    return config


def save_config(config: Config, path: Path | str | None = None) -> None:
    """Save configuration to YAML file."""
    if path is None:
        path = CONFIG_DIR / "default.yaml"

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(exclude={"_config_hash"}, mode="json")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=True, default_flow_style=False)


# Load default config at module import for convenience
_default_config: Config | None = None


def get_config() -> Config:
    """Get the default configuration (loads on first call)."""
    global _default_config
    if _default_config is None:
        _default_config = load_config()
    return _default_config
