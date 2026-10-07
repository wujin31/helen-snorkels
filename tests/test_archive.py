from __future__ import annotations

import gzip
from datetime import timedelta
from pathlib import Path

from snorkel.archive import (
    read_manifest,
    run_archive,
    snapshot_key,
)
from snorkel.fetch.base import FetchContext, Item, ItemError, RawSnapshot, SkipSource
from snorkel.models import CaptureRecord, Location, SourcesConfig, SpotConfig
from snorkel.storage import LocalStorage

from .conftest import MORNING


def ok_source(ctx: FetchContext) -> list[Item]:
    return [RawSnapshot(content=b'{"a": 1}', ext="json", url="https://x.test/ok")]


def partial_source(ctx: FetchContext) -> list[Item]:
    return [
        RawSnapshot(content=b"a,b\n1,2\n", ext="csv", url="https://x.test/1", variant="one"),
        ItemError(error="HTTPStatusError: 500", url="https://x.test/2", variant="two"),
    ]


def boom_source(ctx: FetchContext) -> list[Item]:
    raise RuntimeError("upstream changed")


def skip_source(ctx: FetchContext) -> list[Item]:
    raise SkipSource("station not configured")


def fast_source(ctx: FetchContext) -> list[Item]:
    return [RawSnapshot(content=b"1.2,3.4", ext="csv", url="https://x.test/fast")]


REGISTRY = {
    "t.ok": ok_source,
    "t.partial": partial_source,
    "t.boom": boom_source,
    "t.skip": skip_source,
    "t.fast": fast_source,
}


def make_sources(**overrides: dict[str, object]) -> SourcesConfig:
    sources: dict[str, dict[str, object]] = {
        "t.ok": {"every_minutes": 60},
        "t.partial": {"every_minutes": 30},
        "t.boom": {"every_minutes": 30},
        "t.skip": {"every_minutes": 60},
        "t.fast": {"every_minutes": 15},
    }
    for key, value in overrides.items():
        sources[key].update(value)
    return SourcesConfig(location=Location(lat=32.8666, lon=-117.2571), sources=sources)


def run(storage: LocalStorage, spots: list[SpotConfig], **kwargs: object) -> list[CaptureRecord]:
    defaults: dict[str, object] = {
        "now": MORNING,
        "spots": spots,
        "sources": make_sources(),
        "registry": REGISTRY,
        "log": lambda _msg: None,
    }
    defaults.update(kwargs)
    return run_archive(storage, **defaults)  # type: ignore[arg-type]


def test_one_bad_source_never_stops_the_others(tmp_path: Path, spots: list[SpotConfig]) -> None:
    storage = LocalStorage(tmp_path)
    records = run(storage, spots)
    by_source = {(r.source, r.variant): r for r in records}

    assert by_source[("t.ok", None)].status == "ok"
    assert by_source[("t.partial", "one")].status == "ok"
    assert by_source[("t.partial", "two")].status == "error"
    assert by_source[("t.boom", None)].error == "RuntimeError: upstream changed"
    assert by_source[("t.skip", None)].status == "skipped"
    assert by_source[("t.fast", None)].status == "ok"

    ok = by_source[("t.ok", None)]
    assert ok.key == "raw/t.ok/2026/09/27/160000Z.json.gz"
    assert gzip.decompress(storage.get(ok.key) or b"") == b'{"a": 1}'

    manifest = read_manifest(storage, MORNING.date())
    assert len(manifest) == len(records)


def test_cadence_is_respected_across_runs(tmp_path: Path, spots: list[SpotConfig]) -> None:
    storage = LocalStorage(tmp_path)
    run(storage, spots)
    later = run(storage, spots, now=MORNING + timedelta(minutes=15))
    sources = {r.source for r in later}
    # The 15-min source is due again, errors retry, 30/60-min ok sources wait.
    assert sources == {"t.fast", "t.boom"}

    hour_later = run(storage, spots, now=MORNING + timedelta(minutes=60))
    assert {"t.ok", "t.partial", "t.skip", "t.fast"} <= {r.source for r in hour_later}
    assert len(read_manifest(storage, MORNING.date())) > 0


def test_force_ignores_cadence(tmp_path: Path, spots: list[SpotConfig]) -> None:
    storage = LocalStorage(tmp_path)
    run(storage, spots)
    again = run(storage, spots, now=MORNING + timedelta(minutes=1), force=True, only=["t.ok"])
    assert [r.source for r in again] == ["t.ok"]


def test_snapshot_key_slugs_variants() -> None:
    key = snapshot_key("tides.observed", "9410230_water level", MORNING, "json")
    assert key == "raw/tides.observed/2026/09/27/160000Z_9410230-water-level.json.gz"
