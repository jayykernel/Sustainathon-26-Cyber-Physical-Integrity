"""Parallel, deterministic red-team/blue-team evaluation on fixed seed sets."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any, cast

import numpy as np

from ..active_runner import ActiveTrajectory, run_active_scenario
from ..attacks.runner import AttackTrajectory, run_paired_scenario
from ..config import Config, get_config
from ..eval.metrics import (
    alarm_episode_times,
    confusion_matrix,
    first_detection_episode,
    summarize_detection_runs,
    wilson_interval,
)
from ..localize import LocalizationEngine, load_localization_config
from .schema import EvaluationReportModel

SCENARIOS = ("baseline", "AT1", "AT2", "AT3", "AT4", "AT5", "AT6")
DETECTORS = ("B0", "B1", "B2", "B2_probe_present", "B3")
CHANNEL_BY_ATTACK = {
    "baseline": "none",
    "AT1": "temp",
    "AT2": "temp",
    "AT3": "multi",
    "AT4": "multi",
    "AT5": "command",
    "AT6": "multi",
}


def _run_metrics(
    trace: AttackTrajectory | ActiveTrajectory,
    alarms: np.ndarray,
    attack_id: str,
    config: Config,
) -> dict[str, object]:
    times = np.asarray(trace["t"], dtype=np.float64)
    active = np.asarray(trace["attack_active"], dtype=np.bool_)
    alarm_values = np.asarray(alarms, dtype=np.bool_)
    episodes = alarm_episode_times(alarm_values, times, merge_gap_s=60.0)
    active_indices = np.flatnonzero(active)
    attacked = attack_id != "baseline" and active_indices.size > 0
    onset = float(times[active_indices[0]]) if attacked else None
    false_episodes = [episode for episode in episodes if onset is None or episode < onset]
    detection_episode = first_detection_episode(episodes, onset) if attacked else None
    detected = detection_episode is not None
    delay: float | None = None
    margin: float | None = None
    if detected and onset is not None:
        assert detection_episode is not None
        detected_at = detection_episode
        detection_index = int(np.searchsorted(times, detected_at, side="left"))
        delay = detected_at - onset
        if attack_id == "AT5":
            margin = float(config.plant.V_hazard - trace["V_true"][detection_index])
        else:
            margin = float(config.plant.T_hazard - trace["T_true"][detection_index])
    duration_hours = float(times[-1] - times[0] + config.simulation.dt) / 3600.0
    false_alarm_hours = (
        max(0.0, float(onset - times[0])) / 3600.0 if onset is not None else duration_hours
    )
    hazard = (
        (np.asarray(trace["T_true"]) > config.plant.T_hazard)
        | (np.asarray(trace["V_true"]) > config.plant.V_hazard)
        | (np.asarray(trace["soc_true"]) > 1.02)
    )
    return {
        "detected": detected,
        "attack_activated": attacked,
        "preempted_before_activation": False,
        "delay_s": delay,
        "safety_margin": margin,
        "false_alarm_episodes": len(false_episodes),
        "false_alarm_hours": false_alarm_hours,
        "peak_temperature_c": float(np.max(trace["T_true"])),
        "peak_voltage_v": float(np.max(trace["V_true"])),
        "hazard_event": bool(np.any(hazard)),
        "hazard_samples": int(np.count_nonzero(hazard)),
    }


def _localization_result(
    trace: AttackTrajectory, attack_id: str, config: Config
) -> dict[str, Any]:
    engine = LocalizationEngine(config, load_localization_config())
    actual: list[str] = []
    predicted: list[str] = []
    attack_channel = CHANNEL_BY_ATTACK[attack_id]
    for index, active in enumerate(trace["attack_active"]):
        alarm = bool(trace["B3_alarm"][index])
        output = engine.update(
            float(trace["V_rep"][index]),
            float(trace["I_rep"][index]),
            float(trace["T_rep"][index]),
            float(trace["I_cmd"][index]),
            alarm,
            command_tampered=bool(trace["command_tampered"][index]),
        )
        actual.append(attack_channel if active else "none")
        predicted.append(output["channel"])
    return cast(
        dict[str, Any],
        confusion_matrix(actual, predicted, scenario_id=attack_id),
    )


def _evaluate_one(task: tuple[str, int, int]) -> dict[str, Any]:
    attack_id, seed, duration_s = task
    config = get_config()
    undefended, defended = run_paired_scenario(
        attack_id, seed, config=config, duration_s=duration_s
    )
    active = run_active_scenario(
        attack_id, seed, config=config, duration_s=duration_s
    )
    alarms: dict[str, np.ndarray] = {
        "B0": undefended["B0_alarm"],
        "B1": undefended["B1_alarm"],
        "B2": undefended["B2_alarm"],
        "B2_probe_present": active["B2_alarm"],
        "B3": defended["B3_alarm"],
    }
    traces: dict[str, AttackTrajectory | ActiveTrajectory] = {
        "B0": undefended,
        "B1": undefended,
        "B2": undefended,
        "B2_probe_present": active,
        "B3": defended,
    }
    detector_metrics = {
        detector: _run_metrics(traces[detector], alarms[detector], attack_id, config)
        for detector in DETECTORS
    }
    baseline_attack_active = bool(np.any(undefended["attack_active"]))
    defended_attack_active = bool(np.any(defended["attack_active"]))
    detector_metrics["B3"]["preempted_before_activation"] = (
        attack_id != "baseline" and baseline_attack_active and not defended_attack_active
    )
    paired_hazard = bool(
        (undefended["T_true"] > config.plant.T_hazard).any()
        or (undefended["V_true"] > config.plant.V_hazard).any()
        or (undefended["soc_true"] > 1.02).any()
    )
    defended_hazard = bool(
        (defended["T_true"] > config.plant.T_hazard).any()
        or (defended["V_true"] > config.plant.V_hazard).any()
        or (defended["soc_true"] > 1.02).any()
    )
    paired = {
        "peak_temperature_reduction_c": float(
            np.max(undefended["T_true"]) - np.max(defended["T_true"])
        ),
        "peak_voltage_reduction_v": float(
            np.max(undefended["V_true"]) - np.max(defended["V_true"])
        ),
        "hazard_improvement": paired_hazard and not defended_hazard,
        "undefended_hazard": paired_hazard,
        "defended_hazard": defended_hazard,
        "preempted_before_activation": (
            attack_id != "baseline"
            and bool(np.any(undefended["attack_active"]))
            and not bool(np.any(defended["attack_active"]))
        ),
    }
    localization = _localization_result(defended, attack_id, config)
    return {
        "scenario": attack_id,
        "seed": seed,
        "detectors": detector_metrics,
        "paired_safety": paired,
        "localization": localization,
    }


def run_evaluation(
    *,
    start_seed: int = 1000,
    run_count: int = 200,
    duration_s: int | None = None,
    workers: int | None = None,
    progress: bool = True,
) -> dict[str, Any]:
    """Evaluate all seven scenarios over a deterministic contiguous seed range."""
    if start_seed < 0 or run_count < 1:
        raise ValueError("start_seed must be non-negative and run_count positive")
    config = get_config()
    selected_duration = int(duration_s or config.simulation.duration)
    if selected_duration < 1:
        raise ValueError("duration_s must be positive")
    seed_values = tuple(range(start_seed, start_seed + run_count))
    tasks = [(scenario, seed, selected_duration) for scenario in SCENARIOS for seed in seed_values]
    worker_count = max(1, workers or min(8, len(tasks)))
    # Tiny per-sample matrix solves are slower when every process launches a
    # large OpenBLAS team. Limit worker BLAS pools before Windows spawn inherits env.
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=worker_count) as pool:
        for completed, row in enumerate(pool.map(_evaluate_one, tasks, chunksize=1), start=1):
            rows.append(row)
            if progress and (completed % 20 == 0 or completed == len(tasks)):
                print(f"evaluation: {completed}/{len(tasks)} scenario-seed runs", flush=True)

    by_scenario: dict[str, dict[str, Any]] = {}
    localization_by_scenario: dict[str, Any] = {}
    details: dict[str, list[dict[str, Any]]] = {}
    for scenario in SCENARIOS:
        scenario_rows = [row for row in rows if row["scenario"] == scenario]
        detector_results: dict[str, Any] = {}
        details[scenario] = scenario_rows
        attacked = scenario != "baseline"
        for detector in DETECTORS:
            per_run = [row["detectors"][detector] for row in scenario_rows]
            exposure = sum(float(item["false_alarm_hours"]) for item in per_run)
            detector_results[detector] = summarize_detection_runs(
                per_run,
                attacked=attacked,
                duration_hours=exposure if exposure > 0 else 1e-12,
                safety_unit="V" if scenario == "AT5" else "°C",
            )
        paired_rows = [row["paired_safety"] for row in scenario_rows]
        hazard_improvements = sum(bool(row["hazard_improvement"]) for row in paired_rows)
        detector_results["paired_safety"] = {
            "runs": len(paired_rows),
            "mean_peak_temperature_reduction_c": float(
                np.mean([row["peak_temperature_reduction_c"] for row in paired_rows])
            ),
            "mean_peak_voltage_reduction_v": float(
                np.mean([row["peak_voltage_reduction_v"] for row in paired_rows])
            ),
            "hazard_rate_reduction": float(
                np.mean([row["undefended_hazard"] for row in paired_rows])
                - np.mean([row["defended_hazard"] for row in paired_rows])
            ),
            "hazard_reduction_ci_95": wilson_interval(hazard_improvements, len(paired_rows)),
            "preempted_before_activation_runs": sum(
                bool(row["preempted_before_activation"]) for row in paired_rows
            ),
        }
        by_scenario[scenario] = detector_results
        matrices = [row["localization"] for row in scenario_rows]
        counts = np.sum(np.asarray([matrix["counts"] for matrix in matrices], dtype=np.int64), axis=0)
        samples = sum(int(matrix["samples"]) for matrix in matrices)
        ambiguous = sum(int(matrix["ambiguous_multi"]) for matrix in matrices)
        scored = samples - ambiguous
        correct = sum(
            int(matrix["counts"][index][index])
            for matrix in matrices
            for index in range(len(matrix["labels"]))
        )
        localization_by_scenario[scenario] = {
            "labels": matrices[0]["labels"],
            "counts": counts.tolist(),
            "samples": samples,
            "ambiguous_multi": ambiguous,
            "accuracy_excluding_ambiguous": correct / scored if scored else None,
        }

    report = EvaluationReportModel(
        split="test",
        seeds=seed_values,
        duration_s=selected_duration,
        config_hash=config.config_hash(),
        scenarios=by_scenario,
        localization_confusion=localization_by_scenario,
    )
    output = report.model_dump(mode="json")
    output["details"] = details
    return output
