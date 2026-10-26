"""Small evaluation metrics shared by phase-specific reports."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from statistics import NormalDist, median
from typing import TypedDict

import numpy as np
from scipy.stats import chi2  # type: ignore[import-untyped]


class ConfusionMatrix(TypedDict):
    """Row-normalized labels and raw count matrix with ambiguity accounting."""

    labels: list[str]
    counts: list[list[int]]
    samples: int
    ambiguous_multi: int
    accuracy_excluding_ambiguous: float | None


class DetectionSummary(TypedDict):
    """Detection, alarm burden, safety, and delay statistics for one scenario."""

    runs: int
    detections: int
    attack_activated_runs: int
    preempted_before_activation_runs: int
    detection_rate: float | None
    detection_ci_95: list[float] | None
    median_delay_s: float | None
    delay_iqr_s: list[float] | None
    median_safety_margin: float | None
    safety_margin_unit: str | None
    false_alarm_episodes: int
    false_alarm_hours: float
    false_alarms_per_hour: float
    false_alarm_rate_ci_95: list[float]
    mean_peak_temperature_c: float
    mean_peak_voltage_v: float
    hazard_events: int
    hazard_event_rate: float
    hazard_event_ci_95: list[float]


class RunDetectionMetrics(TypedDict):
    """Scalar metrics collected from one simulation trajectory."""

    detected: bool
    delay_s: float | None
    safety_margin: float | None
    false_alarm_episodes: int
    false_alarm_hours: float
    peak_temperature_c: float
    peak_voltage_v: float
    hazard_event: bool
    hazard_samples: int
    attack_activated: bool
    preempted_before_activation: bool


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> list[float]:
    """Return the two-sided Wilson score interval for a binomial proportion."""
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("require 0 <= successes <= trials")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if trials == 0:
        return [0.0, 1.0]
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    radius = z * np.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials**2)) / denominator
    return [float(max(0.0, center - radius)), float(min(1.0, center + radius))]


def alarm_episode_times(
    alarms: Sequence[bool] | np.ndarray,
    times_s: Sequence[float] | np.ndarray,
    merge_gap_s: float = 60.0,
) -> list[float]:
    """Return episode start times, merging alarms separated by at most `merge_gap_s`."""
    alarm_values = np.asarray(alarms, dtype=np.bool_)
    time_values = np.asarray(times_s, dtype=np.float64)
    if alarm_values.ndim != 1 or time_values.ndim != 1 or alarm_values.size != time_values.size:
        raise ValueError("alarms and times must be equal-length one-dimensional sequences")
    if not np.all(np.isfinite(time_values)) or merge_gap_s < 0:
        raise ValueError("times must be finite and merge gap non-negative")
    indices = np.flatnonzero(alarm_values)
    if not indices.size:
        return []
    episodes = [float(time_values[indices[0]])]
    previous = float(time_values[indices[0]])
    for index in indices[1:]:
        current = float(time_values[index])
        if current - previous > merge_gap_s:
            episodes.append(current)
        previous = current
    return episodes


def first_detection_episode(
    episode_times: Sequence[float], attack_onset_s: float | None
) -> float | None:
    """Return the first newly opened alarm episode at or after attack onset."""
    if attack_onset_s is None:
        return None
    return next((time_s for time_s in episode_times if time_s >= attack_onset_s), None)


def summarize_detection_runs(
    runs: Sequence[RunDetectionMetrics],
    *,
    attacked: bool,
    duration_hours: float,
    safety_unit: str | None,
) -> DetectionSummary:
    """Aggregate per-run detection outputs with Wilson and Poisson intervals."""
    if not runs or duration_hours <= 0 or not np.isfinite(duration_hours):
        raise ValueError("runs must be non-empty and duration_hours positive")
    eligible_runs = [row for row in runs if row["attack_activated"]] if attacked else []
    detections = sum(bool(row["detected"]) for row in eligible_runs)
    delays = [float(row["delay_s"]) for row in runs if row["delay_s"] is not None]
    margins = [float(row["safety_margin"]) for row in runs if row["safety_margin"] is not None]
    false_alarms = sum(int(row["false_alarm_episodes"]) for row in runs)
    false_alarm_hours = sum(float(row["false_alarm_hours"]) for row in runs)
    false_rate = false_alarms / false_alarm_hours if false_alarm_hours else 0.0
    if false_alarms == 0:
        fa_ci = [0.0, float(chi2.ppf(0.975, 2) / (2.0 * false_alarm_hours))]
    else:
        fa_ci = [
            float(chi2.ppf(0.025, 2 * false_alarms) / (2.0 * false_alarm_hours)),
            float(chi2.ppf(0.975, 2 * (false_alarms + 1)) / (2.0 * false_alarm_hours)),
        ]
    hazard_events = sum(bool(row["hazard_event"]) for row in runs)
    return {
        "runs": len(runs),
        "detections": detections,
        "attack_activated_runs": len(eligible_runs),
        "preempted_before_activation_runs": sum(
            bool(row["preempted_before_activation"]) for row in runs
        ),
        "detection_rate": detections / len(eligible_runs) if eligible_runs else None,
        "detection_ci_95": wilson_interval(detections, len(eligible_runs)) if eligible_runs else None,
        "median_delay_s": float(median(delays)) if delays else None,
        "delay_iqr_s": (
            [float(np.quantile(delays, 0.25)), float(np.quantile(delays, 0.75))]
            if delays
            else None
        ),
        "median_safety_margin": float(median(margins)) if margins else None,
        "safety_margin_unit": safety_unit if margins else None,
        "false_alarm_episodes": false_alarms,
        "false_alarm_hours": false_alarm_hours,
        "false_alarms_per_hour": float(false_rate),
        "false_alarm_rate_ci_95": fa_ci,
        "mean_peak_temperature_c": float(np.mean([row["peak_temperature_c"] for row in runs])),
        "mean_peak_voltage_v": float(np.mean([row["peak_voltage_v"] for row in runs])),
        "hazard_events": hazard_events,
        "hazard_event_rate": hazard_events / len(runs),
        "hazard_event_ci_95": wilson_interval(hazard_events, len(runs)),
    }


def confusion_matrix(
    actual: Iterable[str],
    predicted: Iterable[str],
    labels: tuple[str, ...] = ("v", "i", "temp", "multi", "command", "unknown", "none"),
    multi_correct_for: frozenset[str] = frozenset({"AT3", "AT4", "AT6"}),
    scenario_id: str | None = None,
) -> ConfusionMatrix:
    """Build a confusion matrix using SPEC's multi-channel scoring rule."""
    actual_values = list(actual)
    predicted_values = list(predicted)
    if len(actual_values) != len(predicted_values):
        raise ValueError("actual and predicted labels must have the same length")
    if len(set(labels)) != len(labels):
        raise ValueError("labels must be unique")
    indices = {label: index for index, label in enumerate(labels)}
    counts = [[0 for _ in labels] for _ in labels]
    ambiguous = 0
    correct = 0
    for truth, estimate in zip(actual_values, predicted_values, strict=True):
        if truth not in indices or estimate not in indices:
            raise ValueError(f"unknown localization label: {truth!r} or {estimate!r}")
        counts[indices[truth]][indices[estimate]] += 1
        if estimate == "multi" and scenario_id not in multi_correct_for:
            ambiguous += 1
        elif truth == estimate or (estimate == "multi" and scenario_id in multi_correct_for):
            correct += 1
    scored = len(actual_values) - ambiguous
    return {
        "labels": list(labels),
        "counts": counts,
        "samples": len(actual_values),
        "ambiguous_multi": ambiguous,
        "accuracy_excluding_ambiguous": correct / scored if scored else None,
    }
