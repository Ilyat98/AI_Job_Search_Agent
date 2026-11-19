"""Small-sample, human-labeled threshold calibration for vacancy scores."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def load_feedback(path: str | Path) -> list[dict[str, Any]]:
    """Read user decisions from the private CSV feedback file."""
    path = Path(path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def calibrate_threshold(
    rows: list[dict[str, Any]],
    *,
    default_threshold: int,
    minimum_per_class: int = 3,
) -> tuple[int, dict[str, Any]]:
    """Tune the positive cutoff only after enough explicit apply/reject labels."""
    labeled: list[tuple[int, int]] = []
    for row in rows:
        label = str(row.get("label") or "").strip().casefold()
        if label not in {"apply", "reject"}:
            continue
        try:
            score = int(row.get("fit_score"))
        except (TypeError, ValueError):
            continue
        if 0 <= score <= 100:
            labeled.append((score, 1 if label == "apply" else 0))

    positives = sum(label for _, label in labeled)
    negatives = len(labeled) - positives
    metadata = {
        "active": False,
        "samples": len(labeled),
        "positive": positives,
        "negative": negatives,
        "threshold": default_threshold,
    }
    if positives < minimum_per_class or negatives < minimum_per_class:
        return default_threshold, metadata

    candidates = sorted({
        max(35, min(85, score)) for score, _ in labeled
    } | {max(35, min(85, default_threshold))})
    evaluated = []
    for threshold in candidates:
        true_positive = sum(label == 1 and score >= threshold for score, label in labeled)
        true_negative = sum(label == 0 and score < threshold for score, label in labeled)
        balanced_accuracy = 0.5 * (
            true_positive / positives + true_negative / negatives
        )
        precision = true_positive / max(1, sum(score >= threshold for score, _ in labeled))
        evaluated.append((balanced_accuracy, precision, threshold))

    balanced_accuracy, precision, threshold = max(
        evaluated,
        key=lambda item: (item[0], item[1], item[2]),
    )
    metadata.update({
        "active": True,
        "threshold": threshold,
        "balanced_accuracy": round(balanced_accuracy, 3),
        "precision": round(precision, 3),
    })
    return threshold, metadata
