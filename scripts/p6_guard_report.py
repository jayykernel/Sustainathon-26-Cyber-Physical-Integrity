"""Run paired guarded/unguarded P6 attacks and write closed-loop evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from physiguard.attacks.runner import run_paired_scenario
from physiguard.config import CONFIG_DIR, get_config

ROOT = CONFIG_DIR.parent
DEFAULT_JSON = ROOT / "data" / "results" / "p6_closed_loop_report.json"
DEFAULT_MD = ROOT / "data" / "results" / "p6_closed_loop_summary.md"
ATTACKS = ("AT2", "AT3", "AT4", "AT5")


def _summary(trace: Any, config: Any) -> dict[str, float | bool | int]:
    hazard = (
        (trace["T_true"] > config.plant.T_hazard)
        | (trace["V_true"] > config.plant.V_hazard)
        | (trace["soc_true"] > 1.02)
    )
    return {
        "peak_temperature_c": float(np.max(trace["T_true"])),
        "peak_voltage_v": float(np.max(trace["V_true"])),
        "hazard_event": bool(np.any(hazard)),
        "hazard_samples": int(np.count_nonzero(hazard)),
        "command_unsafe_steps": int(np.count_nonzero(trace["command_unsafe"])),
        "safe_mode_steps": int(np.count_nonzero(trace["response_state"] == "SAFE_MODE")),
        "event_count": len(trace["events"]),
    }


def run_report(seed_count: int = 10, output: Path = DEFAULT_JSON) -> dict[str, Any]:
    if seed_count < 1:
        raise ValueError("seed_count must be positive")
    config = get_config()
    result: dict[str, Any] = {
        "validation_seeds": list(range(seed_count)),
        "duration_s": int(config.simulation.duration),
        "config_hash": config.config_hash_short,
        "attacks": {},
    }
    for attack in ATTACKS:
        runs: list[dict[str, Any]] = []
        for seed in range(seed_count):
            undefended, defended = run_paired_scenario(attack, seed, config)
            runs.append(
                {
                    "seed": seed,
                    "undefended": _summary(undefended, config),
                    "defended": _summary(defended, config),
                    "events": defended["events"],
                }
            )
            if (seed + 1) % 5 == 0 or seed + 1 == seed_count:
                print(f"{attack}: completed {seed + 1}/{seed_count} paired seeds", flush=True)

        undefended_rows = [run["undefended"] for run in runs]
        defended_rows = [run["defended"] for run in runs]
        summary = {
            "runs": len(runs),
            "undefended": {
                "mean_peak_temperature_c": float(
                    np.mean([row["peak_temperature_c"] for row in undefended_rows])
                ),
                "mean_peak_voltage_v": float(
                    np.mean([row["peak_voltage_v"] for row in undefended_rows])
                ),
                "hazard_event_rate": float(np.mean([row["hazard_event"] for row in undefended_rows])),
            },
            "defended": {
                "mean_peak_temperature_c": float(
                    np.mean([row["peak_temperature_c"] for row in defended_rows])
                ),
                "mean_peak_voltage_v": float(
                    np.mean([row["peak_voltage_v"] for row in defended_rows])
                ),
                "hazard_event_rate": float(np.mean([row["hazard_event"] for row in defended_rows])),
                "mean_command_unsafe_steps": float(
                    np.mean([row["command_unsafe_steps"] for row in defended_rows])
                ),
                "mean_safe_mode_steps": float(
                    np.mean([row["safe_mode_steps"] for row in defended_rows])
                ),
            },
            "paired_reduction": {
                "peak_temperature_c": float(
                    np.mean(
                        [
                            u["peak_temperature_c"] - d["peak_temperature_c"]
                            for u, d in zip(undefended_rows, defended_rows, strict=True)
                        ]
                    )
                ),
                "peak_voltage_v": float(
                    np.mean(
                        [
                            u["peak_voltage_v"] - d["peak_voltage_v"]
                            for u, d in zip(undefended_rows, defended_rows, strict=True)
                        ]
                    )
                ),
                "hazard_event_rate": float(
                    np.mean([row["hazard_event"] for row in undefended_rows])
                    - np.mean([row["hazard_event"] for row in defended_rows])
                ),
            },
            "per_seed": runs,
        }
        result["attacks"][attack] = summary

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    markdown = [
        "# P6 paired closed-loop validation",
        "",
        f"Validation seeds: 0–{seed_count - 1}; duration: {config.simulation.duration} s per run.",
        "",
        "| Attack | Peak T undefended / defended (°C) | Peak V undefended / defended (V) | Hazard rate undefended / defended | Paired Δ peak T / Δ peak V |",
        "|---|---:|---:|---:|---:|",
    ]
    for attack, summary in result["attacks"].items():
        u = summary["undefended"]
        d = summary["defended"]
        reduction = summary["paired_reduction"]
        markdown.append(
            f"| {attack} | {u['mean_peak_temperature_c']:.2f} / {d['mean_peak_temperature_c']:.2f} "
            f"| {u['mean_peak_voltage_v']:.4f} / {d['mean_peak_voltage_v']:.4f} "
            f"| {u['hazard_event_rate']:.0%} / {d['hazard_event_rate']:.0%} "
            f"| {reduction['peak_temperature_c']:.2f} °C / {reduction['peak_voltage_v']:.4f} V |"
        )
    markdown.extend(
        [
            "",
            "A positive paired delta means the defended run had a lower peak. Failures remain visible in the per-seed JSON and are not removed from the summary.",
        ]
    )
    DEFAULT_MD.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10, help="Number of validation seeds from 0")
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    result = run_report(args.seeds, args.output)
    print(f"Wrote paired guard results to {args.output}")
    print(json.dumps({attack: row["paired_reduction"] for attack, row in result["attacks"].items()}, indent=2))


if __name__ == "__main__":
    main()
