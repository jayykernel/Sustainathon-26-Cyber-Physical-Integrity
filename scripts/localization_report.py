"""Calibrate localization evidence and report AT1/AT2 confusion matrices."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import yaml

from physiguard.attacks.runner import run_attack_scenario
from physiguard.config import CONFIG_DIR, get_config
from physiguard.eval.metrics import confusion_matrix
from physiguard.localize import LocalizationConfig, LocalizationEngine, classify_scores
from physiguard.pipeline import run_pipeline

ROOT = CONFIG_DIR.parent
DEFAULT_OUTPUT = ROOT / "data" / "results" / "localization_report.json"
CHANNEL_LABELS = ("v", "i", "temp", "multi", "command", "unknown", "none")


def _max_healthy_scores(seed: int, config: Any) -> list[float]:
    trajectory = run_pipeline(config, seed=seed, duration_s=config.simulation.duration)
    engine = LocalizationEngine(
        config, LocalizationConfig(score_threshold=2.0, dominance_ratio=1.5)
    )
    maxima: list[float] = []
    for index in range(len(trajectory["t"])):
        result = engine.update(
            float(trajectory["V_rep"][index]),
            float(trajectory["I_rep"][index]),
            float(trajectory["T_rep"][index]),
            float(trajectory["I_cmd"][index]),
            alarm=True,
        )
        if result["evidence"]:
            maxima.append(max(result["evidence"].values()))
    return maxima


def _scenario_predictions(
    attack_id: str,
    seeds: range,
    config: Any,
    duration_s: int,
    settings: LocalizationConfig,
) -> tuple[list[str], list[float]]:
    predictions: list[str] = []
    confidence_values: list[float] = []
    for completed, seed in enumerate(seeds, start=1):
        trace = run_attack_scenario(attack_id, seed, config, duration_s)
        engine = LocalizationEngine(config, settings)
        observed: list[tuple[str, float]] = []
        for index in range(duration_s):
            previous_current = float(trace["I_cmd"][index - 1]) if index else 0.0
            output = engine.update(
                float(trace["V_rep"][index]),
                float(trace["I_rep"][index]),
                float(trace["T_rep"][index]),
                previous_current,
                alarm=bool(trace["B2_alarm"][index]),
            )
            if trace["attack_active"][index] and output["channel"] != "none":
                observed.append((output["channel"], output["confidence"]))
        if not observed:
            predictions.append("none")
            confidence_values.append(0.0)
        else:
            counts = Counter(label for label, _ in observed)
            max_count = max(counts.values())
            selected = next(label for label, _ in observed if counts[label] == max_count)
            predictions.append(selected)
            confidence_values.append(
                float(median(score for label, score in observed if label == selected))
            )
        if completed % 10 == 0 or completed == len(seeds):
            print(
                f"localization final {attack_id}: {completed}/{len(seeds)} runs",
                flush=True,
            )
    return predictions, confidence_values


def make_report(seed_count: int = 100, duration_s: int | None = None) -> dict[str, Any]:
    """Calibrate a shared threshold, tune dominance on half the seeds, and score all seeds."""
    if seed_count < 2:
        raise ValueError("seed_count must be at least two")
    config = get_config()
    duration = duration_s or config.simulation.duration
    seeds = range(seed_count)

    healthy_maxima: list[float] = []
    for seed in seeds:
        healthy_maxima.extend(_max_healthy_scores(seed, config))
        if (seed + 1) % 10 == 0 or seed + 1 == seed_count:
            print(f"localization calibration: {seed + 1}/{seed_count} clean runs", flush=True)
    threshold = float(np.quantile(np.asarray(healthy_maxima), 0.995))

    tuning_seeds = range(max(1, seed_count // 2))
    candidate_ratios = (1.25, 1.5, 2.0, 2.5, 3.0)
    tuning_results: dict[str, Any] = {}
    best_ratio = candidate_ratios[0]
    best_accuracy = -1.0
    for attack_id in ("AT1", "AT2"):
        # Collect telemetry only once; reclassification over ratios uses the same observations.
        trace_rows: list[list[tuple[dict[str, float], bool]]] = []
        for seed in tuning_seeds:
            trace = run_attack_scenario(attack_id, seed, config, duration)
            engine = LocalizationEngine(
                config,
                LocalizationConfig(
                    score_threshold=threshold,
                    dominance_ratio=1.5,
                ),
            )
            rows: list[tuple[dict[str, float], bool]] = []
            for index in range(duration):
                previous_current = float(trace["I_cmd"][index - 1]) if index else 0.0
                output = engine.update(
                    float(trace["V_rep"][index]),
                    float(trace["I_rep"][index]),
                    float(trace["T_rep"][index]),
                    previous_current,
                    alarm=bool(trace["B2_alarm"][index]),
                )
                if trace["attack_active"][index]:
                    rows.append((output["evidence"], bool(trace["B2_alarm"][index])))
            trace_rows.append(rows)
            if (seed + 1) % 10 == 0 or seed + 1 == len(tuning_seeds):
                print(
                    f"localization tuning {attack_id}: {seed + 1}/{len(tuning_seeds)} runs",
                    flush=True,
                )

        expected = "temp"
        for ratio in candidate_ratios:
            setting = LocalizationConfig(
                score_threshold=threshold,
                dominance_ratio=ratio,
            )
            predicted: list[str] = []
            for rows in trace_rows:
                labels = [
                    classify_scores(scores, alarm, setting)["channel"]
                    for scores, alarm in rows
                    if scores
                ]
                detected = [label for label in labels if label != "none"]
                if not detected:
                    predicted.append("none")
                else:
                    counts = Counter(detected)
                    peak = max(counts.values())
                    predicted.append(next(label for label in detected if counts[label] == peak))
            matrix = confusion_matrix(
                [expected] * len(predicted),
                predicted,
                labels=CHANNEL_LABELS,
                scenario_id=attack_id,
            )
            accuracy = matrix["accuracy_excluding_ambiguous"] or 0.0
            tuning_results[f"{attack_id}:{ratio:.2f}"] = {
                "accuracy_excluding_ambiguous": accuracy,
                "ambiguous_multi": matrix["ambiguous_multi"],
            }
            if (accuracy, ratio) > (best_accuracy, best_ratio):
                best_accuracy = accuracy
                best_ratio = ratio

    settings = LocalizationConfig(
        score_threshold=threshold,
        dominance_ratio=best_ratio,
    )
    final_matrices: dict[str, Any] = {}
    final_predictions: dict[str, list[str]] = {}
    final_confidence: dict[str, list[float]] = {}
    for attack_id in ("AT1", "AT2"):
        predictions, confidence = _scenario_predictions(
            attack_id, seeds, config, duration, settings
        )
        actual = ["temp"] * seed_count
        final_matrices[attack_id] = confusion_matrix(
            actual,
            predictions,
            labels=CHANNEL_LABELS,
            scenario_id=attack_id,
        )
        final_predictions[attack_id] = predictions
        final_confidence[attack_id] = confidence

    localization_config_path = CONFIG_DIR / "localization.yaml"
    localization_config_path.write_text(
        yaml.safe_dump(
            {
                "window_s": settings.window_s,
                "score_threshold": settings.score_threshold,
                "dominance_ratio": settings.dominance_ratio,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return {
        "split": "validation",
        "seeds": list(seeds),
        "tuning_seeds": list(tuning_seeds),
        "duration_s": duration,
        "config_hash": config.config_hash(),
        "threshold_calibration": {
            "source": "attack-free validation runs",
            "quantile": 0.995,
            "samples": len(healthy_maxima),
            "score_threshold": threshold,
        },
        "dominance_tuning": {
            "candidate_ratios": candidate_ratios,
            "results": tuning_results,
            "selected_ratio": best_ratio,
            "selection_metric": "accuracy excluding ambiguous multi-channel cases",
        },
        "scoring_note": "AT1 is scored temp-dominant; multi is ambiguous for AT1/AT2. For AT3/AT4/AT6, multi counts as correct.",
        "confusion_matrices": final_matrices,
        "predictions": final_predictions,
        "median_confidence": {
            attack: float(median(values)) if values else 0.0
            for attack, values in final_confidence.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=100, help="validation seeds from zero")
    parser.add_argument("--duration", type=int, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.seeds < 2:
        parser.error("--seeds must be at least two")
    report = make_report(args.seeds, args.duration)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"calibrated localization settings: {report['threshold_calibration']}")
    print(f"selected dominance ratio: {report['dominance_tuning']['selected_ratio']}")
    for attack, matrix in report["confusion_matrices"].items():
        print(f"{attack} confusion: {matrix}")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
