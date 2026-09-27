from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from snorkel.config import load_sources, load_spots
from snorkel.fetch import cdip as cdip_fetch
from snorkel.pipeline import gather
from snorkel.score.config import load_scoring
from snorkel.score.run import score_all

NOW = datetime(2026, 9, 27, 15, 0, tzinfo=UTC)


def test_everything_down_still_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> bytes:
        raise OSError("NetCDF: I/O failure")

    monkeypatch.setattr(cdip_fetch, "dataset_subset_bytes", refuse)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="gone")

    spots, sources = load_spots(), load_sources()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cond = gather(client, NOW, spots, sources)
    doc = score_all(cond, spots, sources, load_scoring())

    assert {s.verdict for s in doc.spots} == {"unknown"}
    assert doc.summary == "Not enough fresh data to call it right now."
    assert doc.best_bet is None
    assert doc.sources and all(h.stale for h in doc.sources)
    assert all(h.error for h in doc.sources if not h.ok)
    # The document must serialize: the page renders from it no matter what.
    assert '"verdict":"unknown"' in doc.model_dump_json()


FIX = Path(__file__).parent / "fixtures"
# The probe that captured these fixtures ran at about 07:10 UTC on 2026-09-27.
CAPTURED = datetime(2026, 9, 27, 7, 20, tzinfo=UTC)


def fixture_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    host = request.url.host
    params = request.url.params
    if host == "api.tidesandcurrents.noaa.gov":
        product = params["product"]
        if product == "predictions":
            name = "9410230_hilo" if params.get("interval") == "hilo" else "9410230_6min"
            return httpx.Response(
                200, content=(FIX / f"tides.predictions/{name}.json").read_bytes()
            )
        return httpx.Response(
            200, content=(FIX / f"tides.observed/9410230_{product}.json").read_bytes()
        )
    if host == "api.open-meteo.com":
        return httpx.Response(
            200, content=(FIX / "weather.openmeteo_forecast/item.json").read_bytes()
        )
    if host == "marine-api.open-meteo.com":
        return httpx.Response(
            200, content=(FIX / "weather.openmeteo_marine/item.json").read_bytes()
        )
    if host == "api.weather.gov" and request.url.path.endswith("/alerts/active"):
        return httpx.Response(
            200, content=(FIX / "weather.nws_alerts/32-842-117-265.json").read_bytes()
        )
    if host == "erddap.cencoos.org":
        [csv] = (FIX / "sccoos.pier").glob("*.csv")
        return httpx.Response(200, content=csv.read_bytes())
    if host == "cosdapps.sandiegocounty.gov":
        if url.endswith("moduleversioninfo") or "moduleversioninfo" in url:
            return httpx.Response(200, json={"versionToken": "MOD"})
        if request.method == "POST":
            return httpx.Response(
                200, content=(FIX / "water_quality.county/sites.json").read_bytes()
            )
    return httpx.Response(404, text=f"no fixture for {url}")


def fixture_netcdf(url: str, cutoff: datetime) -> tuple[bytes, dict[str, object]]:
    if "MOP_alongshore" in url:
        mop = url.rsplit("/", 1)[-1].split("_")[0]
        return (FIX / f"cdip.mop_nowcast/{mop}.nc").read_bytes(), {}
    return (FIX / "cdip.buoy/buoy201.nc").read_bytes(), {}


def test_real_fixtures_score_like_the_live_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """gather() -> score_all() on the responses captured on 2026-09-27.

    That night the live run said: Maybe at the Marine Room (1.5 ft, a Beach
    Hazards Statement in effect) and No at the Cove (~3 ft of NW swell).
    """
    monkeypatch.setattr(cdip_fetch, "dataset_subset_bytes", fixture_netcdf)
    spots, sources = load_spots(), load_sources()
    sources.sources["water_quality.county"]["api_version"] = "API"
    with httpx.Client(transport=httpx.MockTransport(fixture_handler)) as client:
        cond = gather(client, CAPTURED, spots, sources)
    doc = score_all(cond, spots, sources, load_scoring())

    by_id = {s.id: s for s in doc.spots}
    cove, room = by_id["la-jolla-cove"], by_id["marine-room"]
    assert cove.verdict == "no" and cove.reason == "Waves ~3 ft, over 2.5 ft"
    assert cove.conditions.wave_source == "mop"
    assert room.verdict == "maybe"
    assert "NWS Beach Hazards Statement" in room.cautions
    assert room.conditions.hs_ft == pytest.approx(1.5, abs=0.05)
    assert room.window is not None
    assert doc.best_bet == "marine-room"
    assert doc.summary.startswith("Maybe Marine Room")
    stale = {h.id for h in doc.sources if h.stale}
    assert not stale, stale
    assert doc.day.turbidity_ntu is not None and doc.day.wetsuit
    json.loads(doc.model_dump_json())
