"""Validated scenario catalog and guided story-ladder loader."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from ..config import CONFIG_DIR
from .base import AttackError


class ScenarioDefinition(BaseModel):
    """A named demo/evaluation scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    attack: str | None


class StoryStep(BaseModel):
    """One ordered captioned step in the guided narrative."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    caption: str


class ScenarioCatalog(BaseModel):
    """Validated seven-scenario catalog plus its story ladder."""

    scenarios: list[ScenarioDefinition]
    story_ladder: list[StoryStep]


def load_scenarios(path: Path | str | None = None) -> ScenarioCatalog:
    """Load the required scenario IDs and ensure every story step resolves."""
    if path is None:
        path = CONFIG_DIR / "scenarios.yaml"
    scenario_path = Path(path)
    if not scenario_path.exists():
        raise FileNotFoundError(f"Scenario config not found: {scenario_path}")
    with scenario_path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise AttackError("scenario config must be a YAML mapping")
    catalog = ScenarioCatalog.model_validate(data)
    expected = {
        "baseline",
        "spike",
        "drift",
        "replay",
        "model_synthesis",
        "malicious_command",
        "oracle_limit",
    }
    ids = [scenario.id for scenario in catalog.scenarios]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise AttackError("scenario catalog must define the seven required IDs exactly once")
    attack_ids = {"AT1", "AT2", "AT3", "AT4", "AT5", "AT6"}
    for scenario in catalog.scenarios:
        if scenario.attack is not None and scenario.attack not in attack_ids:
            raise AttackError(f"scenario {scenario.id} references unknown attack {scenario.attack}")
    if not catalog.story_ladder:
        raise AttackError("story_ladder must contain at least one step")
    if any(step.scenario_id not in expected for step in catalog.story_ladder):
        raise AttackError("story_ladder references an unknown scenario")
    return catalog
