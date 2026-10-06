"""Parsers against real responses captured by `snorkel probe --save-fixture`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from snorkel.parse import coops, ndbc, nws, openmeteo, sccoos

FIX = Path(__file__).parent / "fixtures"
SPOTS = ["la-jolla-cove", "marine-room"]


def read(rel: str) -> bytes:
    return (FIX / rel).read_bytes()


def test_tide_predictions() -> None:
    points = coops.parse_predictions(read("tides.predictions/9410230_6min.json"))
    assert len(points) > 500
    assert points[0].time.tzinfo is UTC
    assert (points[1].time - points[0].time).total_seconds() == 360
    assert all(-1 < p.height_m < 3 for p in points)


def test_tide_extremes() -> None:
    extremes = coops.parse_extremes(read("tides.predictions/9410230_hilo.json"))
    assert extremes[0].time == datetime(2026, 9, 26, 4, 3, tzinfo=UTC)
    assert extremes[0].kind == "high" and extremes[0].height_m == pytest.approx(1.644)
    assert {e.kind for e in extremes} == {"high", "low"}


def test_pier_wind_and_temp() -> None:
    wind = coops.parse_wind(read("tides.observed/9410230_wind.json"))
    assert wind.obs[0].speed_ms == pytest.approx(0.2)
    assert wind.obs[0].dir_deg == pytest.approx(283.0)
    temp = coops.parse_water_temp(read("tides.observed/9410230_water_temperature.json"))
    assert 10 < temp.temp_c < 30


def test_coops_error_raises() -> None:
    with pytest.raises(ValueError, match="CO-OPS error"):
        coops.parse_wind(b'{"error": {"message": "No data was found."}}')


def test_ndbc_wind() -> None:
    series = ndbc.parse_stdmet_wind(read("weather.ndbc_ljpc1/LJPC1.txt").decode())
    assert [o.time.hour for o in series.obs] == [2, 4, 5]
    assert series.obs[-1].speed_ms == pytest.approx(1.0)
    assert series.obs[-1].gust_ms == pytest.approx(2.1)


def test_openmeteo_forecast_per_spot() -> None:
    parsed = openmeteo.parse_forecast(read("weather.openmeteo_forecast/item.json"), SPOTS)
    wind, precip = parsed["marine-room"]
    assert len(wind.obs) == 144  # 3 past + 3 forecast days, hourly
    assert wind.obs[0].time == datetime(2026, 9, 24, tzinfo=UTC)
    assert len(precip) == 144
    with pytest.raises(ValueError, match="expected 3 locations"):
        openmeteo.parse_forecast(read("weather.openmeteo_forecast/item.json"), [*SPOTS, "x"])


def test_openmeteo_marine_per_spot() -> None:
    waves = openmeteo.parse_marine(read("weather.openmeteo_marine/item.json"), SPOTS)
    cove = waves["la-jolla-cove"]
    assert cove.source == "openmeteo"
    assert cove.obs[0].hs_m == pytest.approx(0.98)
    assert cove.obs[0].dp_deg == 251


def test_nws_alerts_and_activity() -> None:
    alerts = nws.parse_alerts(read("weather.nws_alerts/32-842-117-265.json"))
    events = {a.event for a in alerts}
    assert {"Beach Hazards Statement", "Coastal Flood Advisory"} <= events
    now = datetime(2026, 9, 27, 16, tzinfo=UTC)
    assert {a.event for a in nws.active(alerts, now)} == {"Beach Hazards Statement"}


def test_sccoos_pier_good_values() -> None:
    [csv_file] = (FIX / "sccoos.pier").glob("*.csv")
    temp, chl, turb = sccoos.parse_pier(csv_file.read_bytes())
    assert temp and 15 < temp.temp_c < 30
    assert chl and chl.chl_ug_l == pytest.approx(0.73)
    assert turb and turb.ntu == pytest.approx(0.195)  # median of the last 3 h, not one sample
    assert turb.time == datetime(2026, 9, 27, 6, 52, tzinfo=UTC)


def test_sccoos_rejects_non_csv() -> None:
    with pytest.raises(ValueError):
        sccoos.parse_pier(b"<html>error</html>")


def test_county_sites_and_status() -> None:
    from snorkel.parse import county

    sites = county.parse_sites(read("water_quality.county/sites.json"))
    assert len(sites) == 90
    by_id = {s.id: s for s in sites}
    assert by_id["105"].beach == "La Jolla Cove" and by_id["105"].priority == 1
    assert by_id["51"].location == "Children's Pool" and by_id["51"].priority == 2

    assert county.status_for(["105"], sites).status == "open"
    childrens_pool = county.status_for(["105", "51"], sites)
    assert childrens_pool.status == "advisory"
    assert childrens_pool.detail == "Children's Pool"
    assert county.status_for(["110"], sites).status == "closure"
    with pytest.raises(ValueError, match="not found"):
        county.status_for(["9999"], sites)


def test_nws_surf_zone_forecast_san_diego() -> None:
    from datetime import date

    from snorkel.parse import srf

    fc = srf.parse_srf((FIX / "weather.nws_srf/sgx.json").read_bytes())
    assert fc.zone == "San Diego County Coastal Areas"
    today, wed = fc.periods[0], fc.periods[1]
    assert (today.name, today.day) == ("Today", date(2026, 10, 6))
    assert today.rip_risk == "Moderate" and today.surf_ft == (2, 4) and today.sets_ft is None
    assert today.water_temp_f == (68, 72)
    assert today.remarks == "Mixed swell from 300 and 210 degrees"
    assert (wed.name, wed.day) == ("Wednesday", date(2026, 10, 7))
    assert wed.surf_ft == (2, 4) and wed.sets_ft == 5
    assert fc.for_day(date(2026, 10, 7)) is wed


def test_srf_without_the_zone_is_an_error() -> None:
    import json

    from snorkel.parse import srf

    body = json.dumps({"issuanceTime": "2026-10-06T08:28:00+00:00", "productText": "x"}).encode()
    with pytest.raises(ValueError):
        srf.parse_srf(body)
