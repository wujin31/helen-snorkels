from snorkel.fetch import SOURCES
from snorkel.models import SourcesConfig, SpotConfig


def test_tier1_spots_load(spots: list[SpotConfig]) -> None:
    ids = {s.id for s in spots}
    assert {"la-jolla-cove", "marine-room"} <= ids
    for spot in spots:
        assert 32 < spot.lat < 34 and -118 < spot.lon < -117
        assert spot.tide_station == "9410230"


def test_every_registered_source_is_configured(sources: SourcesConfig) -> None:
    assert set(SOURCES) == set(sources.sources)


def test_cam_is_daylight_gated_and_switchable(sources: SourcesConfig) -> None:
    cam = sources.sources["cam.scripps_pier"]
    assert cam["min_sun_elevation_deg"] >= 0
    assert cam["enabled_env"] == "CAM_CAPTURE_ENABLED"
