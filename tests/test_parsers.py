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


def test_sccoos_pier_latest_good_values() -> None:
    [csv_file] = (FIX / "sccoos.pier").glob("*.csv")
    temp, chl, turb = sccoos.parse_pier(csv_file.read_bytes())
    assert temp and 15 < temp.temp_c < 30
    assert chl and chl.chl_ug_l == pytest.approx(0.73)
    assert turb and turb.ntu == pytest.approx(0.3)
    assert turb.time == datetime(2026, 9, 27, 6, 52, tzinfo=UTC)


def test_sccoos_rejects_non_csv() -> None:
    with pytest.raises(ValueError):
        sccoos.parse_pier(b"<html>error</html>")
