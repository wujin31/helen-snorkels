from pathlib import Path

from snorkel.config import load_spots
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


def test_every_spot_is_wired_to_a_wave_point_and_county_sites() -> None:
    import glob

    from snorkel.parse.county import parse_sites

    [fixture] = glob.glob(str(Path(__file__).parent / "fixtures/water_quality.county/*.json"))
    county_ids = {s.id for s in parse_sites(Path(fixture).read_bytes())}
    spots = load_spots()
    assert len(spots) >= 12
    for spot in spots:
        assert spot.cdip_mop_id and spot.cdip_mop_id.startswith("D"), spot.id
        assert spot.water_quality_ids and set(spot.water_quality_ids) <= county_ids, spot.id
        assert spot.area in {"La Jolla", "Point Loma & Mission Bay", "North County"}, spot.id
        assert 0 <= spot.shore_normal_deg < 360
