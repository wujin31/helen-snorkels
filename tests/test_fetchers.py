from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import unquote

import httpx
import pytest

from snorkel.fetch import cdip, coastwatch, sccoos, tides, water_quality, weather
from snorkel.fetch.base import ItemError, RawSnapshot, SkipSource
from snorkel.models import SourcesConfig, SpotConfig

from .conftest import MORNING, make_ctx


def ok_items(items: list) -> list[RawSnapshot]:
    assert all(isinstance(i, RawSnapshot) for i in items), items
    return items


def test_tide_predictions_request_6min_and_hilo(
    spots: list[SpotConfig], sources: SourcesConfig
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"predictions": [{"t": "2026-09-27 00:00", "v": "1.2"}]})

    items = ok_items(
        tides.capture_predictions(make_ctx(handler, spots, sources, "tides.predictions"))
    )
    assert [i.variant for i in items] == ["9410230_6min", "9410230_hilo"]
    params = dict(seen[0].url.params)
    assert params["station"] == "9410230"
    assert params["datum"] == "MLLW"
    assert params["time_zone"] == "gmt"
    assert params["begin_date"] == "20260926"
    assert params["end_date"] == "20260930"
    assert dict(seen[1].url.params)["interval"] == "hilo"


def test_coops_error_body_is_an_error(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["product"] == "wind":
            return httpx.Response(200, json={"error": {"message": "No data was found."}})
        return httpx.Response(200, json={"data": []})

    items = tides.capture_observed(make_ctx(handler, spots, sources, "tides.observed"))
    errors = [i for i in items if isinstance(i, ItemError)]
    assert [e.variant for e in errors] == ["9410230_wind"]
    assert "No data was found" in errors[0].error
    assert len(items) == len(tides.OBSERVED_PRODUCTS)


def test_ndbc_is_trimmed_to_recent_rows(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    text = (
        "#YY  MM DD hh mm WDIR WSPD GST\n"
        "#yr  mo dy hr mn degT m/s  m/s\n"
        "2026 09 27 15 54 270  3.1  4.0\n"
        "2026 09 27 12 00 260  2.0  3.0\n"
        "2026 09 20 12 00 250  1.0  2.0\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=text)

    [item] = ok_items(weather.capture_ndbc(make_ctx(handler, spots, sources, "weather.ndbc_ljpc1")))
    body = item.content.decode()
    assert item.variant == "LJPC1"
    assert "2026 09 27 15 54" in body and "2026 09 27 12 00" in body
    assert "2026 09 20" not in body
    assert body.startswith("#YY")


def test_openmeteo_batches_all_spots(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{}, {}])

    ctx = make_ctx(handler, spots, sources, "weather.openmeteo_forecast")
    [item] = ok_items(weather.capture_openmeteo_forecast(ctx))
    params = dict(seen[0].url.params)
    assert params["latitude"].count(",") == len(spots) - 1
    assert params["wind_speed_unit"] == "ms"
    assert "precipitation" in params["hourly"]
    assert item.meta["spots"] == [s.id for s in spots]

    ctx = make_ctx(handler, spots, sources, "weather.openmeteo_marine")
    ok_items(weather.capture_openmeteo_marine(ctx))
    assert "swell_wave_period" in dict(seen[1].url.params)["hourly"]


def test_nws_grid_follows_points_lookup(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    grid = "https://api.weather.gov/gridpoints/SGX/53,20"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == "application/geo+json"
        if "/points/" in request.url.path:
            return httpx.Response(200, json={"properties": {"forecastGridData": grid}})
        assert str(request.url) == grid
        return httpx.Response(200, json={"properties": {}})

    [item] = ok_items(
        weather.capture_nws_grid(make_ctx(handler, spots, sources, "weather.nws_grid"))
    )
    assert item.variant == "sgx-53-20"


def test_nws_points_failure_is_an_item_error(
    spots: list[SpotConfig], sources: SourcesConfig
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"title": "Data Unavailable For Requested Point"})

    [item] = weather.capture_nws_grid(make_ctx(handler, spots, sources, "weather.nws_grid"))
    assert isinstance(item, ItemError)


def test_nws_alerts_one_per_point(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": []})

    items = ok_items(
        weather.capture_nws_alerts(make_ctx(handler, spots, sources, "weather.nws_alerts"))
    )
    assert len(items) == len(sources.sources["weather.nws_alerts"]["points"])


def test_sccoos_pier_url_uses_relative_time() -> None:
    url = sccoos.pier_url(
        "https://erddap.cencoos.org/erddap/", "scripps-pier-automated-shore-sta-1", 2
    )
    assert url == (
        "https://erddap.cencoos.org/erddap/tabledap/scripps-pier-automated-shore-sta-1.csv"
        "?&time%3E=now-2hours"
    )


JS = (
    'controller.callDataAction("ScreenDataSetGetSiteById", '
    '"screenservices/CoSD_Beach_Water_CW/MainFlow/HomeBlockNew/ScreenDataSetGetSiteById", '
    '"NEWAPI", callContext);'
)
SITES = {
    "Id": "31",
    "BeachName": "La Jolla Cove",
    "LocationName": "La Jolla Cove",
    "PriorityMax": 0,
}


def county_handler(
    seen: list[httpx.Request], stale_first: bool
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("moduleversioninfo"):
            return httpx.Response(200, json={"versionToken": "MOD"})
        if request.url.path.endswith(".mvc.js"):
            return httpx.Response(200, text=JS)
        body = json.loads(request.content)
        assert request.headers["x-csrftoken"] == water_quality.ANONYMOUS_CSRF
        assert body["versionInfo"]["moduleVersion"] == "MOD"
        if stale_first and body["versionInfo"]["apiVersion"] != "NEWAPI":
            return httpx.Response(200, json={"versionInfo": {"hasApiVersionChanged": True}})
        return httpx.Response(
            200,
            json={
                "versionInfo": {"hasApiVersionChanged": False},
                "data": {"List": {"List": [SITES]}},
            },
        )

    return handler


def test_county_sites(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    seen: list[httpx.Request] = []
    ctx = make_ctx(county_handler(seen, stale_first=False), spots, sources, "water_quality.county")
    [item] = ok_items(water_quality.capture_county(ctx))
    assert item.variant == "sites"
    assert item.meta == {"sites": 1, "api_version": "NEWAPI"}
    assert json.loads(item.content)["data"]["List"]["List"][0]["BeachName"] == "La Jolla Cove"


def test_county_rediscovers_a_stale_api_version(
    spots: list[SpotConfig], sources: SourcesConfig
) -> None:
    seen: list[httpx.Request] = []
    handler = county_handler(seen, stale_first=True)
    ctx = make_ctx(handler, spots, sources, "water_quality.county", api_version="OLD")
    [item] = ok_items(water_quality.capture_county(ctx))
    posts = [r for r in seen if r.method == "POST"]
    assert [json.loads(r.content)["versionInfo"]["apiVersion"] for r in posts] == ["OLD", "NEWAPI"]
    assert item.meta["api_version"] == "NEWAPI"


def test_county_failure_is_an_item_error(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    [item] = water_quality.capture_county(make_ctx(handler, spots, sources, "water_quality.county"))
    assert isinstance(item, ItemError)


def test_unconfigured_sources_skip(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not fetch")

    with pytest.raises(SkipSource):
        coastwatch.capture_viirs(make_ctx(handler, spots, sources, "coastwatch.viirs", datasets=[]))
    unconfigured = [s.model_copy(update={"cdip_mop_id": None}) for s in spots]
    with pytest.raises(SkipSource):
        cdip.capture_mop_nowcast(make_ctx(handler, unconfigured, sources, "cdip.mop_nowcast"))


def test_coastwatch_griddap_url() -> None:
    url = coastwatch.griddap_url(
        "https://coastwatch.noaa.gov/erddap",
        {"id": "ds", "var": "kd_490", "altitude": True},
        32.85,
        -117.27,
        0.05,
    )
    assert url.startswith("https://coastwatch.noaa.gov/erddap/griddap/ds.nc?")
    assert unquote(url.split("?", 1)[1]) == (
        "kd_490[(last)][(0.0)][(32.8000):(32.9000)][(-117.3200):(-117.2200)]"
    )


def test_mop_forecast_uses_fileserver(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"CDF\x01")

    configured = [s.model_copy(update={"cdip_mop_id": "D0520"}) for s in spots]
    ctx = make_ctx(handler, configured, sources, "cdip.mop_forecast")
    [item] = ok_items(cdip.capture_mop_forecast(ctx))
    assert seen == [
        "https://thredds.cdip.ucsd.edu/thredds/fileServer/cdip/model/MOP_alongshore/D0520_forecast.nc"
    ]
    assert item.variant == "D0520"


def test_now_is_utc() -> None:
    assert MORNING.utcoffset() is not None and json.dumps(MORNING.isoformat())
