"""Fetch everything the scorer needs, fresh, and turn it into `Conditions`.

Reuses the archiver's capture functions (with longer look-backs where the
scorer needs history) and the pure parsers. Each input is gathered on its own:
a failure becomes a failed SourceResult with the error, never an exception.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

import httpx

from snorkel.archive import run_with_timeout
from snorkel.fetch import cdip as cdip_fetch
from snorkel.fetch import sccoos as sccoos_fetch
from snorkel.fetch import tides as tides_fetch
from snorkel.fetch import water_quality as wq_fetch
from snorkel.fetch import weather as weather_fetch
from snorkel.fetch.base import FetchContext, ItemError, RawSnapshot, SourceFn, describe_error
from snorkel.models import SourcesConfig, SpotConfig
from snorkel.observations import (
    Alert,
    Chlorophyll,
    PrecipObs,
    SourceResult,
    Tides,
    Turbidity,
    WaterQuality,
    WaterTemp,
    WaveSeries,
    WindSeries,
)
from snorkel.parse import cdip as cdip_parse
from snorkel.parse import coops, county, ndbc, nws, openmeteo, sccoos
from snorkel.score.conditions import Conditions

T = TypeVar("T")
TIMEOUT_S = 90.0
HISTORY_HOURS = 72  # wave history for the decayed swell-energy feature


class Gatherer:
    def __init__(
        self,
        client: httpx.Client,
        now: datetime,
        spots: list[SpotConfig],
        sources: SourcesConfig,
    ) -> None:
        self.client = client
        self.now = now
        self.spots = spots
        self.sources = sources
        self._cache: dict[str, list[RawSnapshot | ItemError]] = {}

    def capture(
        self, source_id: str, fn: SourceFn, **overrides: Any
    ) -> list[RawSnapshot | ItemError]:
        key = f"{source_id}:{sorted(overrides.items())}"
        if key not in self._cache:
            params = {**self.sources.sources.get(source_id, {}), **overrides}
            ctx = FetchContext(
                client=self.client,
                now=self.now,
                spots=self.spots,
                params=params,
                location=self.sources.location,
            )
            self._cache[key] = run_with_timeout(lambda: fn(ctx), TIMEOUT_S)
        return self._cache[key]

    def item(
        self, source_id: str, fn: SourceFn, variant: str | None = None, **overrides: Any
    ) -> RawSnapshot:
        items = self.capture(source_id, fn, **overrides)
        for item in items:
            if variant is None or item.variant == variant:
                if isinstance(item, ItemError):
                    raise RuntimeError(item.error)
                return item
        raise RuntimeError(f"{source_id}: no item {variant!r}")

    def result(
        self,
        name: str,
        build: Callable[[], T],
        valid_at: Callable[[T], datetime | None] = lambda _v: None,
    ) -> SourceResult[T]:
        try:
            value = build()
        except Exception as exc:
            return SourceResult(
                source=name, ok=False, fetched_at=self.now, error=describe_error(exc)
            )
        return SourceResult(
            source=name, ok=True, fetched_at=self.now, value=value, valid_at=valid_at(value)
        )


def _last_time(obs: list[Any]) -> datetime | None:
    return max((o.time for o in obs), default=None)


def gather(
    client: httpx.Client,
    now: datetime,
    spots: list[SpotConfig],
    sources: SourcesConfig,
) -> Conditions:
    g = Gatherer(client, now, spots, sources)
    cond = Conditions(now=now)
    station = spots[0].tide_station
    spot_ids = [s.id for s in spots]

    # Tides: 6-minute curve plus highs and lows.
    def tides() -> Tides:
        curve = coops.parse_predictions(
            g.item("tides.predictions", tides_fetch.capture_predictions, f"{station}_6min").content
        )
        turns = coops.parse_extremes(
            g.item("tides.predictions", tides_fetch.capture_predictions, f"{station}_hilo").content
        )
        return Tides(station=station, points=curve, extremes=turns)

    cond.tides = g.result("tides", tides, lambda _t: now)

    # Waves: MOP at the spot, else the Scripps Nearshore buoy, else Open-Meteo.
    def marine() -> dict[str, WaveSeries]:
        body = g.item("weather.openmeteo_marine", weather_fetch.capture_openmeteo_marine).content
        return openmeteo.parse_marine(body, spot_ids)

    marine_result = g.result("openmeteo_marine", marine)
    for spot in spots:
        candidates: list[SourceResult[WaveSeries]] = []
        if spot.cdip_mop_id:
            mop = spot.cdip_mop_id
            candidates.append(
                g.result(
                    f"mop {mop}",
                    lambda mop=mop: cdip_parse.parse_waves(
                        g.item(
                            "cdip.mop_nowcast",
                            cdip_fetch.capture_mop_nowcast,
                            mop,
                            hours=HISTORY_HOURS,
                        ).content,
                        "mop",
                        mop,
                    ),
                    lambda w: _last_time(w.obs),
                )
            )
        if spot.cdip_buoy:
            buoy = spot.cdip_buoy
            candidates.append(
                g.result(
                    f"buoy {buoy}",
                    lambda buoy=buoy: cdip_parse.parse_waves(
                        g.item(
                            "cdip.buoy", cdip_fetch.capture_buoy, f"buoy{buoy}", hours=HISTORY_HOURS
                        ).content,
                        "buoy",
                        buoy,
                    ),
                    lambda w: _last_time(w.obs),
                )
            )
        if marine_result.ok and marine_result.value and spot.id in marine_result.value:
            series = marine_result.value[spot.id]
            candidates.append(
                SourceResult(
                    source="openmeteo_marine",
                    ok=True,
                    fetched_at=now,
                    value=series,
                    valid_at=now,  # a model: current by construction
                )
            )
        fresh = [
            c
            for c in candidates
            if c.ok
            and c.value
            and c.value.obs
            and (c.valid_at is None or now - c.valid_at <= timedelta(hours=4))
        ]
        if fresh:
            cond.waves[spot.id] = fresh[0]
        else:
            errors = "; ".join(f"{c.source}: {c.error or 'stale'}" for c in candidates)
            cond.waves[spot.id] = SourceResult(
                source="waves", ok=False, fetched_at=now, error=errors or marine_result.error
            )

    # Wind now: the pier anemometer (CO-OPS, else NDBC's copy).
    def pier_wind() -> WindSeries:
        try:
            body = g.item("tides.observed", tides_fetch.capture_observed, f"{station}_wind").content
            series = coops.parse_wind(body)
            if series.obs:
                return series
        except Exception:
            pass
        text = g.item("weather.ndbc_ljpc1", weather_fetch.capture_ndbc).content.decode()
        return ndbc.parse_stdmet_wind(text)

    cond.wind_obs = g.result("wind_obs", pier_wind, lambda w: _last_time(w.obs))

    # Forecast wind and rain per spot.
    def forecast() -> dict[str, tuple[WindSeries, list[PrecipObs]]]:
        body = g.item(
            "weather.openmeteo_forecast", weather_fetch.capture_openmeteo_forecast
        ).content
        return openmeteo.parse_forecast(body, spot_ids)

    fc = g.result("openmeteo_forecast", forecast, lambda _v: now)
    for spot in spots:
        if fc.ok and fc.value and spot.id in fc.value:
            wind, precip = fc.value[spot.id]
            cond.wind_forecast[spot.id] = SourceResult(
                source="openmeteo", ok=True, fetched_at=now, value=wind, valid_at=now
            )
            cond.precip[spot.id] = SourceResult(
                source="openmeteo", ok=True, fetched_at=now, value=precip, valid_at=now
            )
        else:
            failed: SourceResult[Any] = SourceResult(
                source="openmeteo", ok=False, fetched_at=now, error=fc.error
            )
            cond.wind_forecast[spot.id] = failed
            cond.precip[spot.id] = failed

    # Pier sensors: temperature, chlorophyll, turbidity.
    def pier() -> tuple[WaterTemp | None, Chlorophyll | None, Turbidity | None]:
        return sccoos.parse_pier(g.item("sccoos.pier", sccoos_fetch.capture_pier, hours=6).content)

    pier_result = g.result("sccoos_pier", pier)
    temp, chl, turb = (
        pier_result.value if pier_result.ok and pier_result.value else (None, None, None)
    )

    def water_temp() -> WaterTemp:
        if temp is not None:
            return temp
        body = g.item(
            "tides.observed", tides_fetch.capture_observed, f"{station}_water_temperature"
        ).content
        return coops.parse_water_temp(body)

    cond.water_temp = g.result("water_temp", water_temp, lambda t: t.time)
    cond.chlorophyll = _from_optional("chlorophyll", chl, pier_result, now)
    cond.turbidity = _from_optional("turbidity", turb, pier_result, now)

    # NWS alerts, in effect now, across all configured points.
    def alerts() -> list[Alert]:
        items = g.capture("weather.nws_alerts", weather_fetch.capture_nws_alerts)
        seen: dict[tuple[str, str], Alert] = {}
        oks = [i for i in items if isinstance(i, RawSnapshot)]
        if not oks:
            errors = [i.error for i in items if isinstance(i, ItemError)]
            raise RuntimeError("; ".join(errors) or "no alert responses")
        for item in oks:
            for alert in nws.active(nws.parse_alerts(item.content), now):
                seen[(alert.event, alert.headline)] = alert
        return list(seen.values())

    cond.alerts = g.result("alerts", alerts, lambda _a: now)

    # Water quality per spot, from the county's own site list.
    def county_sites() -> list[county.CountySite]:
        return county.parse_sites(
            g.item("water_quality.county", wq_fetch.capture_county, "sites").content
        )

    sites = g.result("water_quality", county_sites, lambda _s: now)
    for spot in spots:

        def one(spot: SpotConfig = spot) -> WaterQuality:
            if not sites.ok or sites.value is None:
                raise RuntimeError(sites.error or "county sites unavailable")
            if not spot.water_quality_ids:
                raise RuntimeError("no county sampling site configured for this spot")
            return county.status_for(spot.water_quality_ids, sites.value)

        cond.water_quality[spot.id] = g.result("water_quality", one, lambda _q: now)
    return cond


def _from_optional(
    name: str,
    value: T | None,
    parent: SourceResult[Any],
    now: datetime,
) -> SourceResult[T]:
    if value is None:
        return SourceResult(
            source=name,
            ok=False,
            fetched_at=now,
            error=parent.error or f"no valid {name} reading",
        )
    return SourceResult(
        source=name, ok=True, fetched_at=now, value=value, valid_at=getattr(value, "time", None)
    )
