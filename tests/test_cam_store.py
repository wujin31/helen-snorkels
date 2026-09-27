"""The cam model against an archive: calibrate on demand, read each frame once,
keep readings private unless publishing is switched on."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from snorkel.archive import append_manifest
from snorkel.config import load_sources, load_spots
from snorkel.cv import store
from snorkel.cv.pier_cam import load_cam_model
from snorkel.models import CaptureRecord
from snorkel.score.config import load_scoring
from snorkel.score.run import empty_conditions, score_all
from snorkel.storage import LocalStorage

from .test_pier_cam import frame

NOW = datetime(2026, 9, 28, 19, 0, tzinfo=UTC)


def jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return out.getvalue()


def archive_frames(storage: LocalStorage, times: list[datetime], c_per_m: float = 0.15) -> None:
    for i, t in enumerate(times):
        key = f"frames/cam.scripps_pier/{t:%Y/%m/%d/%H%M%SZ}.jpg"
        storage.put(key, jpeg(frame(c_per_m, seed=i)), "image/jpeg")
        record = CaptureRecord(
            source="cam.scripps_pier",
            run_at=t,
            status="ok",
            key=key,
            meta={"brightness": 150.0, "sun_elevation": 40.0, "frozen": False, "motion": 1.2},
        )
        append_manifest(storage, t.date(), [record])


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    s = LocalStorage(tmp_path)
    archive_frames(s, [NOW - timedelta(minutes=15 * k) for k in range(8, 0, -1)])
    return s


def test_catch_up_calibrates_then_reads_each_frame_once(storage: LocalStorage) -> None:
    cfg = load_cam_model()
    latest = store.catch_up(storage, cfg, NOW)
    assert latest is not None and latest.qc is None and latest.pilings_visible == 4
    assert store.load_rois(storage) is not None
    assert len(store.read_logged(storage, NOW.date())) == 8

    store.catch_up(storage, cfg, NOW + timedelta(minutes=5))  # nothing new to read
    assert len(store.read_logged(storage, NOW.date())) == 8

    archive_frames(storage, [NOW + timedelta(minutes=10)], c_per_m=0.8)
    newer = store.catch_up(storage, cfg, NOW + timedelta(minutes=12))
    assert newer is not None and newer.pilings_visible == 2
    assert len(store.read_logged(storage, NOW.date())) == 9


def test_an_old_frame_is_no_reading_of_now(storage: LocalStorage) -> None:
    assert store.catch_up(storage, load_cam_model(), NOW + timedelta(hours=2)) is None
    assert len(store.read_logged(storage, NOW.date())) == 8  # still logged


def test_nothing_archived_means_no_reading(tmp_path: Path) -> None:
    empty = LocalStorage(tmp_path)
    assert store.catch_up(empty, load_cam_model(), NOW) is None
    assert store.load_rois(empty) is None


def test_the_page_gets_only_the_bracket_and_only_when_handed_readings(
    storage: LocalStorage,
) -> None:
    store.catch_up(storage, load_cam_model(), NOW)
    readings = store.read_logged(storage, NOW.date())
    spots, sources, cfg = load_spots(), load_sources(), load_scoring()

    private = score_all(empty_conditions(NOW), spots, sources, cfg)
    assert private.cam is not None and private.cam.reading is None
    assert "contrasts" not in private.model_dump_json()

    shown = score_all(empty_conditions(NOW), spots, sources, cfg, cam_readings=readings)
    assert shown.cam is not None and shown.cam.reading is not None
    assert shown.cam.reading.vis_ft == (30, 40)
    assert len(shown.cam.readings_today) == 8
    assert "contrasts" not in shown.model_dump_json()  # raw measurements stay private


def test_the_cli_keeps_readings_private_by_default(
    storage: LocalStorage, capsys: pytest.CaptureFixture[str]
) -> None:
    from snorkel.cli import _cam_model

    assert _cam_model(storage, NOW) is None  # publish: false
    out = capsys.readouterr().out
    assert "(private)" in out
    assert "ft" not in out and "piling" not in out
