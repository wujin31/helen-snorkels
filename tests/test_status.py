from __future__ import annotations

from datetime import date

from snorkel.models import SourcesConfig
from snorkel.score.run import CAM_SOURCE, cam_info, empty_conditions
from snorkel.sun import sun_times

from .conftest import MORNING


def test_cam_section_comes_from_capture_config(sources: SourcesConfig) -> None:
    cam = cam_info(sources, date(2026, 9, 27))
    assert cam is not None
    assert cam.watch_url.startswith("https://hdontap.com/stream/")
    # HDOnTap only lets its own and UCSD sites frame the player: no inline
    # player until Scripps adds this site.
    assert cam.embed_url is None
    assert "safe" not in cam.caption.lower()


def test_cam_light_sits_inside_daylight(sources: SourcesConfig) -> None:
    cam = cam_info(sources, date(2026, 9, 27))
    assert cam is not None and len(cam.light) == 2
    loc = sources.location
    for window, day in zip(cam.light, (date(2026, 9, 27), date(2026, 9, 28)), strict=True):
        sun = sun_times(loc.lat, loc.lon, day)
        assert sun.sunrise < window.start < window.end < sun.sunset


def test_no_cam_configured_means_no_cam_section(sources: SourcesConfig) -> None:
    trimmed = sources.model_copy(
        update={"sources": {k: v for k, v in sources.sources.items() if k != CAM_SOURCE}}
    )
    assert cam_info(trimmed, date(2026, 9, 27)) is None


def test_status_doc_carries_the_cam(sources: SourcesConfig) -> None:
    from snorkel.config import load_spots
    from snorkel.score.config import load_scoring
    from snorkel.score.run import score_all

    doc = score_all(empty_conditions(MORNING), load_spots(), sources, load_scoring())
    assert doc.cam is not None and doc.cam.reading is None
    assert '"cam":{"title"' in doc.model_dump_json()
