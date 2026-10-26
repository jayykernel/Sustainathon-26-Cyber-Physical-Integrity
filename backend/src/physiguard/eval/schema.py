"""Validated on-disk schema for reproducible red-team evaluation results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DetectionMetricsModel(StrictModel):
    runs: int = Field(ge=1)
    detections: int = Field(ge=0)
    attack_activated_runs: int = Field(ge=0)
    preempted_before_activation_runs: int = Field(ge=0)
    detection_rate: float | None = Field(default=None, ge=0, le=1)
    detection_ci_95: tuple[float, float] | None = None
    median_delay_s: float | None = Field(default=None, ge=0)
    delay_iqr_s: tuple[float, float] | None = None
    median_safety_margin: float | None = None
    safety_margin_unit: str | None = None
    false_alarm_episodes: int = Field(ge=0)
    false_alarm_hours: float = Field(ge=0)
    false_alarms_per_hour: float = Field(ge=0)
    false_alarm_rate_ci_95: tuple[float, float]
    mean_peak_temperature_c: float
    mean_peak_voltage_v: float
    hazard_events: int = Field(ge=0)
    hazard_event_rate: float = Field(ge=0, le=1)
    hazard_event_ci_95: tuple[float, float]


class PairedSafetyModel(StrictModel):
    runs: int = Field(ge=1)
    mean_peak_temperature_reduction_c: float
    mean_peak_voltage_reduction_v: float
    hazard_rate_reduction: float
    hazard_reduction_ci_95: tuple[float, float]
    preempted_before_activation_runs: int = Field(ge=0)


class ScenarioResultModel(StrictModel):
    B0: DetectionMetricsModel
    B1: DetectionMetricsModel
    B2: DetectionMetricsModel
    B2_probe_present: DetectionMetricsModel
    B3: DetectionMetricsModel
    paired_safety: PairedSafetyModel


class EvaluationReportModel(StrictModel):
    schema_version: Literal[1] = 1
    split: Literal["test"] = "test"
    seeds: tuple[int, ...] = Field(min_length=1)
    duration_s: int = Field(gt=0)
    config_hash: str = Field(min_length=1)
    scenarios: dict[str, ScenarioResultModel]
    localization_confusion: dict[str, object]


class EvaluationMetadataModel(StrictModel):
    git_hash: str
    git_dirty: bool
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_hash: str
    seeds: tuple[int, ...]
    runtime_seconds: float = Field(ge=0)
    generated_at_utc: str
    workers: int = Field(ge=1)
