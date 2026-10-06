from __future__ import annotations

import gzip
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from snorkel.archive import (
    is_due,
    manifest_key,
    read_manifest,
    run_archive,
    run_with_timeout,
    snapshot_key,
)
from snorkel.fetch.base import FetchContext, Item, ItemError, RawSnapshot, SkipSource
from snorkel.models import CaptureRecord, Location, SourcesConfig, SpotConfig
from snorkel.storage import LocalStorage

from .conftest import MORNING, NIGHT


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


def frame_source(ctx: FetchContext) -> list[Item]:
    return [RawSnapshot(content=b"\xff\xd8jpeg", ext="jpg", url="https://x.test/cam")]


REGISTRY = {
    "t.ok": ok_source,
    "t.partial": partial_source,
    "t.boom": boom_source,
    "t.skip": skip_source,
    "t.cam": frame_source,
}


def make_sources(**overrides: dict[str, object]) -> SourcesConfig:
    sources: dict[str, dict[str, object]] = {
        "t.ok": {"every_minutes": 60},
        "t.partial": {"every_minutes": 30},
        "t.boom": {"every_minutes": 30},
        "t.skip": {"every_minutes": 60},
        "t.cam": {
            "every_minutes": 15,
            "min_sun_elevation_deg": 2,
            "enabled_env": "CAM_CAPTURE_ENABLED",
        },
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
        "environ": {},
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
    assert by_source[("t.cam", None)].status == "ok"

    ok = by_source[("t.ok", None)]
    assert ok.key == "raw/t.ok/2026/09/27/160000Z.json.gz"
    assert gzip.decompress(storage.get(ok.key) or b"") == b'{"a": 1}'
    frame = by_source[("t.cam", None)]
    assert frame.key == "frames/t.cam/2026/09/27/160000Z.jpg"
    assert storage.get(frame.key) == b"\xff\xd8jpeg"  # frames aren't gzipped

    manifest = read_manifest(storage, MORNING.date())
    assert len(manifest) == len(records)


def test_cadence_is_respected_across_runs(tmp_path: Path, spots: list[SpotConfig]) -> None:
    storage = LocalStorage(tmp_path)
    run(storage, spots)
    later = run(storage, spots, now=MORNING + timedelta(minutes=15))
    sources = {r.source for r in later}
    # 15-min cam is due again, errors retry, 30/60-min ok sources wait.
    assert sources == {"t.cam", "t.boom"}

    hour_later = run(storage, spots, now=MORNING + timedelta(minutes=60))
    assert {"t.ok", "t.partial", "t.skip", "t.cam"} <= {r.source for r in hour_later}
    assert len(read_manifest(storage, MORNING.date())) > 0


def test_force_ignores_cadence(tmp_path: Path, spots: list[SpotConfig]) -> None:
    storage = LocalStorage(tmp_path)
    run(storage, spots)
    again = run(storage, spots, now=MORNING + timedelta(minutes=1), force=True, only=["t.ok"])
    assert [r.source for r in again] == ["t.ok"]


def test_cam_waits_for_daylight(tmp_path: Path, spots: list[SpotConfig]) -> None:
    records = run(LocalStorage(tmp_path), spots, now=NIGHT)
    assert "t.cam" not in {r.source for r in records}
    assert "t.ok" in {r.source for r in records}


def test_cam_kill_switch(tmp_path: Path, spots: list[SpotConfig]) -> None:
    storage = LocalStorage(tmp_path)
    off = run(storage, spots, environ={"CAM_CAPTURE_ENABLED": "false"})
    assert "t.cam" not in {r.source for r in off}
    on = run(LocalStorage(tmp_path / "b"), spots, environ={"CAM_CAPTURE_ENABLED": ""})
    assert "t.cam" in {r.source for r in on}


def test_unknown_only_is_an_error(tmp_path: Path, spots: list[SpotConfig]) -> None:
    with pytest.raises(ValueError, match="unknown source"):
        run(LocalStorage(tmp_path), spots, only=["nope"])


def test_manifest_survives_a_corrupt_line(tmp_path: Path, spots: list[SpotConfig]) -> None:
    storage = LocalStorage(tmp_path)
    run(storage, spots)
    key = manifest_key(MORNING.date())
    storage.put(key, (storage.get(key) or b"") + b"not json\n", "application/x-ndjson")
    assert len(read_manifest(storage, MORNING.date())) == 6


def test_is_due_slack_absorbs_cron_jitter() -> None:
    last = CaptureRecord(source="s", run_at=MORNING, status="ok")
    assert not is_due([last], 60, MORNING + timedelta(minutes=50))
    assert is_due([last], 60, MORNING + timedelta(minutes=56))
    assert is_due([last], 15, MORNING + timedelta(minutes=11))
    errored = CaptureRecord(source="s", run_at=MORNING, status="error")
    assert is_due([errored], 60, MORNING + timedelta(minutes=1))


def test_hung_source_times_out() -> None:
    with pytest.raises(TimeoutError):
        run_with_timeout(lambda: time.sleep(5), 0.05)
    assert run_with_timeout(lambda: 42, 1) == 42


def test_snapshot_key_slugs_variants() -> None:
    key = snapshot_key("tides.observed", "9410230_water level", MORNING, "json")
    assert key == "raw/tides.observed/2026/09/27/160000Z_9410230-water-level.json.gz"


def test_purge_cam_deletes_frames_and_cam_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date

    from typer.testing import CliRunner

    from snorkel.archive import append_manifest
    from snorkel.cli import app

    storage = LocalStorage(tmp_path)
    frame = "frames/cam.scripps_pier/2026/09/28/160000Z.jpg"
    storage.put(frame, b"\xff\xd8", "image/jpeg")
    storage.put("state/cam_rois.json", b"{}", "application/json")
    storage.put("state/cam_readings/2026-09-28.jsonl", b"{}\n", "application/x-ndjson")
    storage.put("raw/tides.observed/2026/09/28/x.json.gz", b"keep", "application/gzip")
    append_manifest(
        storage,
        date(2026, 9, 28),
        [
            CaptureRecord(
                source="cam.scripps_pier",
                run_at=datetime(2026, 9, 28, 16, tzinfo=UTC),
                status="ok",
                key=frame,
            )
        ],
    )
    result = CliRunner().invoke(
        app, ["purge-cam", "--storage", f"local:{tmp_path}", "--since", "2026-09-28"]
    )
    assert result.exit_code == 0, result.output
    assert "deleted 3 objects" in result.output
    assert storage.get(frame) is None and storage.get("state/cam_rois.json") is None
    assert storage.get("raw/tides.observed/2026/09/28/x.json.gz") == b"keep"
