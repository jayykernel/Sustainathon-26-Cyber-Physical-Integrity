"""Attack-free trace generation and empirical passive-detector calibration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..config import Config, DetectionConfig
from ..detectors.cusum import CUSUM
from ..detectors.nis import NISWindow
from ..detectors.range_check import RangeCheck
from ..pipeline import run_pipeline
from ..plant import vary_unit_config
from ..twin import EKF


@dataclass(frozen=True)
class PassiveTrace:
    """One attack-free run's innovations and range-check outcomes."""

    seed: int
    nis: NDArray[np.float64]
    z_v: NDArray[np.float64]
    z_t: NDArray[np.float64]
    z_i: NDArray[np.float64]
    range_alarm: NDArray[np.bool_]

    @property
    def samples(self) -> int:
        """Number of innovation samples in this trace."""
        return int(self.nis.size)


def generate_passive_trace(config: Config, seed: int, duration_s: int) -> PassiveTrace:
    """Run a seeded attack-free plant and collect standardized EKF residuals."""
    unit_config = vary_unit_config(config, seed)
    trajectory = run_pipeline(
        unit_config, seed=seed, duration_s=duration_s, unit_variation=False
    )
    if trajectory["t"].size < 2:
        raise ValueError("duration_s must produce at least two pipeline samples")

    ekf = EKF(unit_config)
    ekf.initialize(float(trajectory["V_rep"][0]), float(trajectory["T_rep"][0]))
    range_check = RangeCheck(unit_config)
    range_flags = [
        bool(
            range_check.check(
                float(trajectory["V_rep"][0]),
                float(trajectory["I_rep"][0]),
                float(trajectory["T_rep"][0]),
            )
        )
    ]
    nis_values: list[float] = []
    z_v: list[float] = []
    z_t: list[float] = []
    z_i: list[float] = []
    for index in range(1, trajectory["t"].size):
        current_cmd = float(trajectory["I_cmd"][index])
        ekf.predict(current_cmd)
        result = ekf.update(
            float(trajectory["V_rep"][index]),
            float(trajectory["T_rep"][index]),
            current_cmd,
            I_meas=float(trajectory["I_rep"][index]),
        )
        nis_values.append(result["NIS"])
        z_v.append(float(result["nu"][0] / result["innovation_std"][0]))
        z_t.append(float(result["nu"][1] / result["innovation_std"][1]))
        z_i.append(float(result["r_I"] / unit_config.sensors.I_residual_sigma))
        range_flags.append(
            bool(
                range_check.check(
                    float(trajectory["V_rep"][index]),
                    float(trajectory["I_rep"][index]),
                    float(trajectory["T_rep"][index]),
                )
            )
        )

    return PassiveTrace(
        seed=seed,
        nis=np.asarray(nis_values, dtype=np.float64),
        z_v=np.asarray(z_v, dtype=np.float64),
        z_t=np.asarray(z_t, dtype=np.float64),
        z_i=np.asarray(z_i, dtype=np.float64),
        range_alarm=np.asarray(range_flags[1:], dtype=np.bool_),
    )


def _event_count(alarm: NDArray[np.bool_]) -> int:
    """Count rising edges, so a sustained alarm is one false-alarm episode."""
    if alarm.size == 0:
        return 0
    previous = np.concatenate((np.array([False]), alarm[:-1]))
    return int(np.count_nonzero(alarm & ~previous))


def _family_alarms(
    trace: PassiveTrace,
    base_config: Config,
    detection: DetectionConfig,
) -> tuple[NDArray[np.bool_], NDArray[np.bool_], NDArray[np.bool_]]:
    """Replay NIS, CUSUM, and range tests over one stored trace."""
    nis_detector = NISWindow(detection.NIS_window, detection.NIS_threshold)
    cusum_detectors = {
        channel: CUSUM(
            detection.CUSUM_kappa, detection.CUSUM_h, detection.CUSUM_deadband
        )
        for channel in ("V", "T", "I")
    }
    nis_alarm = np.zeros(trace.samples, dtype=np.bool_)
    cusum_alarm = np.zeros(trace.samples, dtype=np.bool_)
    for index in range(trace.samples):
        nis_alarm[index] = nis_detector.update(float(trace.nis[index])).alarm
        channel_alarms = [
            cusum_detectors[channel].update(float(residual[index])).alarm
            for channel, residual in (("V", trace.z_v), ("T", trace.z_t), ("I", trace.z_i))
        ]
        cusum_alarm[index] = any(channel_alarms)
    return nis_alarm, cusum_alarm, trace.range_alarm.copy()


def summarize_false_alarms(
    traces: list[PassiveTrace], base_config: Config, detection: DetectionConfig
) -> dict[str, float | int]:
    """Return per-family and combined alarm episode rates per simulated hour."""
    nis_events = 0
    cusum_events = 0
    range_events = 0
    combined_events = 0
    total_samples = 0
    for trace in traces:
        nis_alarm, cusum_alarm, range_alarm = _family_alarms(
            trace, base_config, detection
        )
        combined = nis_alarm | cusum_alarm | range_alarm
        nis_events += _event_count(nis_alarm)
        cusum_events += _event_count(cusum_alarm)
        range_events += _event_count(range_alarm)
        combined_events += _event_count(combined)
        total_samples += trace.samples
    exposure_hours = total_samples * base_config.simulation.dt / 3600.0
    if exposure_hours <= 0:
        raise ValueError("false-alarm exposure must be positive")
    return {
        "exposure_hours": exposure_hours,
        "nis_events": nis_events,
        "cusum_events": cusum_events,
        "range_events": range_events,
        "combined_events": combined_events,
        "nis_fa_per_hour": nis_events / exposure_hours,
        "cusum_fa_per_hour": cusum_events / exposure_hours,
        "range_fa_per_hour": range_events / exposure_hours,
        "combined_fa_per_hour": combined_events / exposure_hours,
    }


def _nis_events_at(
    traces: list[PassiveTrace], window: int, threshold: float
) -> int:
    events = 0
    for trace in traces:
        detector = NISWindow(window, threshold)
        alarms = np.fromiter(
            (detector.update(float(value)).alarm for value in trace.nis),
            dtype=np.bool_,
            count=trace.samples,
        )
        events += _event_count(alarms)
    return events


def _cusum_events_at(traces: list[PassiveTrace], detection: DetectionConfig, h: float) -> int:
    events = 0
    for trace in traces:
        detectors = {
            channel: CUSUM(detection.CUSUM_kappa, h, detection.CUSUM_deadband)
            for channel in ("V", "T", "I")
        }
        alarms = np.zeros(trace.samples, dtype=np.bool_)
        for index in range(trace.samples):
            channel_alarms = [
                detectors[channel].update(float(values[index])).alarm
                for channel, values in (("V", trace.z_v), ("T", trace.z_t), ("I", trace.z_i))
            ]
            alarms[index] = any(channel_alarms)
        events += _event_count(alarms)
    return events


def _select_threshold(
    maximum: float, event_budget: int, count_events: Callable[[float], int]
) -> float:
    """Find the lowest monotone threshold whose calibration count meets budget."""
    low = 1e-9
    high = max(maximum * 1.01, 1e-6)
    for _ in range(28):
        middle = 0.5 * (low + high)
        if count_events(middle) > event_budget:
            low = middle
        else:
            high = middle
    return high


def calibrate_thresholds(
    traces: list[PassiveTrace], base_config: Config
) -> tuple[DetectionConfig, dict[str, float | int]]:
    """Calibrate NIS/CUSUM thresholds on supplied validation traces only."""
    if not traces:
        raise ValueError("at least one validation trace is required")
    trace_seeds = [trace.seed for trace in traces]
    validation_seeds = set(base_config.detection.calibration_seeds)
    if len(set(trace_seeds)) != len(trace_seeds):
        raise ValueError("validation traces must not contain duplicate seeds")
    if not set(trace_seeds).issubset(validation_seeds):
        raise ValueError("calibration traces contain seeds outside the configured validation split")
    detection = base_config.detection.model_copy(deep=True)
    exposure_hours = sum(trace.samples for trace in traces) * base_config.simulation.dt / 3600.0
    budget_per_family = int(np.floor(detection.FA_target * exposure_hours / 3.0))
    maximum_nis_window_sum = max(
        float(np.sum(trace.nis[i : i + detection.NIS_window]))
        for trace in traces
        for i in range(max(1, trace.samples - detection.NIS_window + 1))
    )
    detection.NIS_threshold = _select_threshold(
        maximum_nis_window_sum,
        budget_per_family,
        lambda value: _nis_events_at(traces, detection.NIS_window, value),
    )
    detection.CUSUM_h = _select_threshold(
        1000.0,
        budget_per_family,
        lambda value: _cusum_events_at(traces, detection, value),
    )
    report = summarize_false_alarms(traces, base_config, detection)
    return detection, report
