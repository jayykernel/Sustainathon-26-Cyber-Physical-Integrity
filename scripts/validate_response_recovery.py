"""Measure response-state recovery on validation-only simulation seeds."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from physiguard.attacks.runner import run_attack_scenario
from physiguard.config import get_config
from physiguard.eval.metrics import alarm_episode_times, first_detection_episode

SCENARIOS = ("baseline", "AT1", "AT2", "AT3", "AT4", "AT5", "AT6")
OUTPUT = Path(__file__).resolve().parents[1] / "data/results/p10_response_validation.json"


def _run_one(task: tuple[str, int, int]) -> dict[str, Any]:
    """Run one defended validation trajectory and summarize response evidence."""
    scenario, seed, duration_s = task
    config = get_config()
    trace = run_attack_scenario(scenario, seed, config, duration_s, defended=True)
    times = np.asarray(trace["t"], dtype=np.float64)
    alarms = np.asarray(trace["B3_alarm"], dtype=np.bool_)
    active = np.asarray(trace["attack_active"], dtype=np.bool_)
    episodes = alarm_episode_times(alarms, times, merge_gap_s=60.0)
    onset_indices = np.flatnonzero(active)
    onset = float(times[onset_indices[0]]) if scenario != "baseline" and onset_indices.size else None
    detection = first_detection_episode(episodes, onset) if onset is not None else None
    return {
        "scenario": scenario,
        "seed": seed,
        "duration_h": float(times[-1] - times[0] + config.simulation.dt) / 3600.0,
        "alarm_episodes": len(episodes),
        "detected": detection is not None,
        "response_states": sorted({str(state) for state in trace["response_state"]}),
        "event_codes": [event["code"] for event in trace["events"]],
        "hazard": bool(
            np.any(np.asarray(trace["T_true"]) > config.plant.T_hazard)
            or np.any(np.asarray(trace["V_true"]) > config.plant.V_hazard)
            or np.any(np.asarray(trace["soc_true"]) > 1.02)
        ),
    }


def main() -> None:
    """Run fixed validation seeds only and write split-labeled evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-runs", type=int, default=100)
    parser.add_argument("--attack-runs", type=int, default=10)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--duration", type=int, default=3600)
    args = parser.parse_args()
    if args.baseline_runs < 1 or args.attack_runs < 1 or args.workers < 1 or args.duration < 1:
        parser.error("run counts, workers, and duration must be positive")
    if args.baseline_runs > 100 or args.attack_runs > 100:
        parser.error("validation seeds are limited to 0–99")

    tasks = [("baseline", seed, args.duration) for seed in range(args.baseline_runs)]
    tasks.extend(
        (scenario, seed, args.duration)
        for scenario in SCENARIOS[1:]
        for seed in range(args.attack_runs)
    )
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_run_one, tasks, chunksize=1))

    summary: dict[str, dict[str, Any]] = {}
    for scenario in SCENARIOS:
        scenario_rows = [row for row in rows if row["scenario"] == scenario]
        if not scenario_rows:
            continue
        episodes = sum(int(row["alarm_episodes"]) for row in scenario_rows)
        hours = sum(float(row["duration_h"]) for row in scenario_rows)
        summary[scenario] = {
            "runs": len(scenario_rows),
            "B3_alarm_episodes": episodes,
            "B3_alarm_episodes_per_hour": episodes / hours,
            "attack_detection_rate": (
                sum(bool(row["detected"]) for row in scenario_rows) / len(scenario_rows)
                if scenario != "baseline"
                else None
            ),
            "response_state_counts": {
                state: sum(state in row["response_states"] for row in scenario_rows)
                for state in ("SUSPECT", "CONFIRMED", "SAFE_MODE")
            },
            "hazard_runs": sum(bool(row["hazard"]) for row in scenario_rows),
        }

    output = {
        "split": "validation",
        "seed_ranges": {"baseline": [0, args.baseline_runs - 1], "attacks": [0, args.attack_runs - 1]},
        "duration_s": args.duration,
        "config_hash": get_config().config_hash(),
        "scenarios": summary,
        "details": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "details"}, indent=2))
    print(f"Saved validation-only details to {OUTPUT}")


if __name__ == "__main__":
    main()
