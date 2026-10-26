"""Small evaluation metrics shared by phase-specific reports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict


class ConfusionMatrix(TypedDict):
    """Row-normalized labels and raw count matrix with ambiguity accounting."""

    labels: list[str]
    counts: list[list[int]]
    samples: int
    ambiguous_multi: int
    accuracy_excluding_ambiguous: float | None


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
