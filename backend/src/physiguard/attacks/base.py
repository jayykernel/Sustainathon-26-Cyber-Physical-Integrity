"""Validated attack definitions and common deterministic attack interface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import numpy as np
import yaml
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from ..config import CONFIG_DIR, Config


class AttackError(ValueError):
    """Raised for invalid attack definitions or missing attacker context."""


class Telemetry(TypedDict):
    """Reported voltage, current, and temperature channels."""

    V_rep: float
    I_rep: float
    T_rep: float


class TruthState(TypedDict):
    """Plant truth intentionally excludes actuator command and probe state."""

    soc_true: float
    V_true: float
    T_true: float


class AttackDefinition(BaseModel):
    """One validated attack specification loaded from attacks.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str
    knowledge_level: str
    onset_s: int | None = None
    duration_s: int | None = Field(default=None, gt=0)
    parameters: dict[str, float | int]


@dataclass(frozen=True)
class AttackContext:
    """Restricted context for attackers without actuator/probe oracle access."""


@dataclass(frozen=True)
class ReplayContext(AttackContext):
    """Recorded attack-free telemetry available to the replay attacker."""

    telemetry: Mapping[str, NDArray[np.float64]]


@dataclass(frozen=True)
class OracleContext(AttackContext):
    """A2-only context exposing the actual actuator command."""

    I_cmd: float


def load_attack_definitions(
    path: Path | str | None = None,
) -> tuple[tuple[int, int], dict[str, AttackDefinition]]:
    """Load and validate the six configured attacks and randomized onset range."""
    if path is None:
        path = CONFIG_DIR / "attacks.yaml"
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Attack config not found: {config_path}")
    with config_path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise AttackError("attack config must be a YAML mapping")
    onset_range = data.get("onset_range_s")
    if (
        not isinstance(onset_range, list)
        or len(onset_range) != 2
        or not all(isinstance(value, int) for value in onset_range)
        or onset_range[0] < 0
        or onset_range[1] < onset_range[0]
    ):
        raise AttackError("onset_range_s must be two ordered non-negative integers")
    raw_attacks = data.get("attacks")
    required = {f"AT{index}" for index in range(1, 7)}
    if not isinstance(raw_attacks, dict) or set(raw_attacks) != required:
        raise AttackError("attacks.yaml must define AT1 through AT6 exactly once")
    definitions = {
        attack_id: AttackDefinition.model_validate(spec)
        for attack_id, spec in raw_attacks.items()
    }
    return (onset_range[0], onset_range[1]), definitions


class AttackBase:
    """Common hooks for telemetry, physical, and upstream-request attacks."""

    attack_id = ""

    def __init__(
        self,
        definition: AttackDefinition,
        config: Config,
        onset_range_s: tuple[int, int],
        seed: int,
    ) -> None:
        self.definition = definition
        self.config = config
        self.parameters = definition.parameters
        self.rng = np.random.default_rng(seed)
        if definition.onset_s is None:
            self.onset_s = int(self.rng.integers(onset_range_s[0], onset_range_s[1] + 1))
        else:
            self.onset_s = definition.onset_s
        self.duration_s = definition.duration_s

    @property
    def knowledge_level(self) -> str:
        """Attacker information boundary documented in the frozen attack config."""
        return self.definition.knowledge_level

    def is_active(self, t_s: float) -> bool:
        """Return whether the configured time window is active."""
        if t_s < self.onset_s:
            return False
        return self.duration_s is None or t_s < self.onset_s + self.duration_s

    def apply(
        self,
        t_s: float,
        truth: TruthState,
        reported: Telemetry,
        rng: np.random.Generator,
        ctx: AttackContext,
    ) -> Telemetry:
        """Transform telemetry; the default implementation leaves it unchanged."""
        del t_s, truth, rng, ctx
        return reported.copy()

    def physical(self, t_s: float, plant: object) -> None:
        """Apply an optional physical payload to the plant."""
        del t_s, plant

    def request(self, t_s: float, I_req: float, truth: TruthState) -> float:
        """Transform an upstream current request; default is a pass-through."""
        del t_s, truth
        return I_req


def make_attack(
    attack_id: str,
    config: Config,
    seed: int,
    path: Path | str | None = None,
) -> AttackBase:
    """Create an attack with deterministic onset and per-run random state."""
    onset_range_s, definitions = load_attack_definitions(path)
    if attack_id not in definitions:
        raise AttackError(f"unknown attack ID: {attack_id}")
    from .implementations import (
        AT1Spike,
        AT2Drift,
        AT3Replay,
        AT4ModelSynthesis,
        AT5MaliciousCommand,
        AT6Oracle,
    )

    constructors: dict[str, type[AttackBase]] = {
        "AT1": AT1Spike,
        "AT2": AT2Drift,
        "AT3": AT3Replay,
        "AT4": AT4ModelSynthesis,
        "AT5": AT5MaliciousCommand,
        "AT6": AT6Oracle,
    }
    return constructors[attack_id](definitions[attack_id], config, onset_range_s, seed)
