"""Tests for atomic publish writes and dead-source miss tracking."""

from __future__ import annotations

import json
from pathlib import Path

from snorkel.misses import (
    ALERT_AFTER,
    dead_sources,
    load_misses,
    save_misses,
    state_path_for,
    update_misses,
)
from snorkel.publish.io import append_jsonl_atomic, atomic_write_text


def test_atomic_write_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "status.json"
    atomic_write_text(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
    assert list((tmp_path / "sub").glob("*.tmp")) == []


def test_append_jsonl_atomic_appends_and_preserves(tmp_path: Path) -> None:
    target = tmp_path / "history.jsonl"
    target.write_text('{"t": 1}\n', encoding="utf-8")
    append_jsonl_atomic(target, [{"t": 2}, {"t": 3}])
    lines = target.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"t": 1}, {"t": 2}, {"t": 3}]


def test_misses_increment_reset_and_alert() -> None:
    misses = update_misses({}, [("cdip", False), ("nws", True)])
    assert misses == {"cdip": 1}
    assert dead_sources(misses) == []
    misses = update_misses(misses, [("cdip", False), ("nws", False)])
    assert misses == {"cdip": 2, "nws": 1}
    assert dead_sources(misses) == ["cdip"]
    assert ALERT_AFTER == 2
    misses = update_misses(misses, [("cdip", True)])
    assert misses == {}


def test_misses_state_roundtrip(tmp_path: Path) -> None:
    state = tmp_path / "source-misses.json"
    assert load_misses(state) == {}
    save_misses(state, {"cdip": 2})
    assert load_misses(state) == {"cdip": 2}
    assert state_path_for(tmp_path / "status.json") == state
