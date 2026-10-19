"""Consecutive-miss tracking for dead-source alerts (issue #19/#20).

Each scoring run records, per source id, how many runs in a row it has been
unusable (not ok). State lives in a small sidecar JSON file next to
status.json so no schema change to the published document is needed. When a
source misses ALERT_AFTER consecutive runs, the score command prints an
ALERT line and the workflow surfaces it instead of silently publishing
stale-as-live data.
"""

from __future__ import annotations

import json
from pathlib import Path

ALERT_AFTER = 2  # consecutive missed runs before a source is called dead


def state_path_for(status_path: Path) -> Path:
    return status_path.with_name("source-misses.json")


def load_misses(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items() if isinstance(v, int) and v > 0}


def update_misses(previous: dict[str, int], health: list[tuple[str, bool]]) -> dict[str, int]:
    """Roll miss counters forward: ok resets to 0 (dropped), failure increments."""
    updated: dict[str, int] = {}
    for source_id, ok in health:
        if ok:
            continue
        updated[source_id] = previous.get(source_id, 0) + 1
    return updated


def dead_sources(misses: dict[str, int], threshold: int = ALERT_AFTER) -> list[str]:
    """Source ids that missed at least `threshold` runs in a row, sorted."""
    return sorted(sid for sid, count in misses.items() if count >= threshold)


def save_misses(path: Path, misses: dict[str, int]) -> None:
    from snorkel.publish.io import atomic_write_text

    atomic_write_text(path, json.dumps(misses, indent=1, sort_keys=True) + "\n")
