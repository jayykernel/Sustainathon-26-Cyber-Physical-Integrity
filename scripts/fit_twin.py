"""Fit the nominal one-RC polarization parameters on synthetic validation data."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from physiguard.config import Config, load_config
from physiguard.plant import plant_advance

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "default.yaml"
VALIDATION_SEED = 10_000


@dataclass(frozen=True)
class TwinFit:
    """Fitted one-RC model and its voltage-polarization error."""

    validation_seed: int
    R1_n: float
    tau1_n: float
    polarization_rmse_v: float


def fit_twin_parameters(config: Config, seed: int = VALIDATION_SEED) -> TwinFit:
    """Fit R and tau to attack-free, plant-generated validation excitation."""
    rng = np.random.default_rng(seed)
    levels = np.array([0.0, 25.0, 45.0, 65.0, 90.0])
    profile = np.repeat(rng.choice(levels, size=240), 15).astype(np.float64)
    truth = plant_advance(profile, config)
    target = truth["v1"] + truth["v2"]
    dt_s = float(config.simulation.dt)

    def predict(log_parameters: np.ndarray) -> np.ndarray:
        resistance, tau = np.exp(log_parameters)
        decay = np.exp(-dt_s / tau)
        estimate = np.empty_like(profile)
        state = 0.0
        for index, current_a in enumerate(profile):
            state = state * decay + resistance * (1.0 - decay) * current_a
            estimate[index] = state
        return estimate

    fit = least_squares(
        lambda log_parameters: predict(log_parameters) - target,
        np.log([config.plant.R1 + config.plant.R2, (config.plant.tau1 + config.plant.tau2) / 2]),
        bounds=(np.log([1e-5, 1.0]), np.log([0.02, 2000.0])),
        method="trf",
    )
    resistance, tau = np.exp(fit.x)
    rmse = float(np.sqrt(np.mean(np.square(predict(fit.x) - target))))
    return TwinFit(seed, float(resistance), float(tau), rmse)


def write_fit(path: Path, fit: TwinFit) -> None:
    """Update only the fitted resistance and time constant in the YAML source."""
    text = path.read_text(encoding="utf-8")
    for key, value in (("R1_n", fit.R1_n), ("tau1_n", fit.tau1_n)):
        pattern = rf"(?m)^(\s*{key}:\s*)[-+0-9.eE]+"
        text, count = re.subn(pattern, rf"\g<1>{value:.10g}", text, count=1)
        if count != 1:
            raise ValueError(f"Could not find exactly one {key} field in {path}")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=VALIDATION_SEED)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--write", action="store_true", help="write fitted parameters to config")
    args = parser.parse_args()

    config = load_config(args.config)
    fit = fit_twin_parameters(config, args.seed)
    if args.write:
        write_fit(args.config, fit)
    print(json.dumps(asdict(fit), indent=2))


if __name__ == "__main__":
    main()
