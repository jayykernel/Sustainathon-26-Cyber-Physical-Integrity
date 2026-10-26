"""Plot honest and under-reported-temperature charging trajectories."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from physiguard.config import get_config
from physiguard.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs" / "screens" / "p1-plausibility.png"
    )
    args = parser.parse_args()

    config = get_config()
    honest = run_pipeline(
        config, seed=args.seed, duration_s=args.duration, unit_variation=False
    )
    underreported = run_pipeline(
        config,
        seed=args.seed,
        duration_s=args.duration,
        underreport_temperature=True,
        unit_variation=False,
    )
    hijacked = run_pipeline(
        config,
        seed=args.seed,
        duration_s=args.duration,
        hijack_cv_current_a=150.0,
        unit_variation=False,
    )
    minutes = honest["t"] / 60.0

    figure, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout="constrained")
    axes[0].plot(minutes, honest["T_true"], label="Honest true temperature", color="#147d64")
    axes[0].plot(
        minutes,
        underreported["T_true"],
        label="Under-reported true temperature",
        color="#c44e52",
    )
    axes[0].plot(
        minutes,
        underreported["T_rep"],
        label="Under-reported temperature telemetry",
        color="#8172b3",
        alpha=0.75,
    )
    axes[0].axhline(config.plant.T_warn, color="#dd8452", linestyle="--", label="Warning limit")
    axes[0].axhline(config.plant.T_hazard, color="#c44e52", linestyle=":", label="Hazard limit")
    axes[0].set_ylabel("Temperature (°C)")
    axes[0].legend(loc="upper left", ncols=2, fontsize=8)
    axes[0].grid(alpha=0.2)

    axes[1].plot(minutes, honest["V_true"], label="Honest terminal voltage", color="#147d64")
    axes[1].plot(
        minutes,
        underreported["V_true"],
        label="Under-reported terminal voltage",
        color="#c44e52",
        alpha=0.8,
    )
    axes[1].plot(
        minutes,
        hijacked["V_true"],
        label="150 A CV request hijack",
        color="#4c72b0",
        alpha=0.8,
    )
    axes[1].axhline(config.plant.V_max, color="#dd8452", linestyle="--", label="Vmax")
    axes[1].axhline(config.plant.V_hazard, color="#c44e52", linestyle=":", label="Voltage hazard")
    axes[1].set_xlabel("Time (minutes)")
    axes[1].set_ylabel("Voltage (V)")
    axes[1].legend(loc="lower right", ncols=2, fontsize=8)
    axes[1].grid(alpha=0.2)
    figure.suptitle(f"PhysiGuard P1 nominal charge trajectories (seed {args.seed})")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=160)
    plt.close(figure)

    hot = np.flatnonzero(underreported["T_true"] > config.plant.T_hazard)
    attack_onsets = np.flatnonzero(hijacked["hijack_active"])
    voltage_hazards = np.flatnonzero(
        hijacked["hijack_active"] & (hijacked["V_true"] > config.plant.V_hazard)
    )
    soc_hazards = np.flatnonzero(
        hijacked["hijack_active"] & (hijacked["soc_true"] > 1.02)
    )
    print(f"Wrote {args.output}")
    print(
        "Honest: "
        f"max T={honest['T_true'].max():.2f} °C, "
        f"max V={honest['V_true'].max():.4f} V, "
        f"final SOC={honest['soc_true'][-1]:.4f}"
    )
    print(
        "Under-reported: "
        f"max T={underreported['T_true'].max():.2f} °C, "
        f"first thermal hazard={hot[0] * config.simulation.dt / 60:.2f} min"
        if hot.size
        else "Under-reported run did not reach thermal hazard"
    )
    if attack_onsets.size and (voltage_hazards.size or soc_hazards.size):
        hazard_candidates: list[int] = []
        if voltage_hazards.size:
            hazard_candidates.append(int(voltage_hazards[0]))
        if soc_hazards.size:
            hazard_candidates.append(int(soc_hazards[0]))
        first_hazard = min(hazard_candidates)
        print(
            "150 A CV hijack: "
            f"first active at {attack_onsets[0] * config.simulation.dt / 60:.2f} min, "
            f"hazard after {(first_hazard - attack_onsets[0]) * config.simulation.dt:.0f} s"
        )
    else:
        print("150 A CV hijack did not reach a hazard")


if __name__ == "__main__":
    main()
