"""Open-Meteo forecast and marine JSON (multi-location, timezone=GMT)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from snorkel.observations import PrecipObs, WaveObs, WaveSeries, WindObs, WindSeries


def _locations(body: bytes, spot_ids: list[str]) -> dict[str, dict[str, Any]]:
    data = json.loads(body)
    if isinstance(data, dict):
        if data.get("error"):
            raise ValueError(f"Open-Meteo error: {data.get('reason')}")
        data = [data]
    if len(data) != len(spot_ids):
        raise ValueError(f"expected {len(spot_ids)} locations, got {len(data)}")
    return dict(zip(spot_ids, data, strict=True))


def _times(hourly: dict[str, list[Any]]) -> list[datetime]:
    return [datetime.fromisoformat(t).replace(tzinfo=UTC) for t in hourly["time"]]


def parse_forecast(
    body: bytes, spot_ids: list[str]
) -> dict[str, tuple[WindSeries, list[PrecipObs]]]:
    """Per spot: hourly wind (m/s, from `wind_speed_unit=ms`) and precipitation (mm/h)."""
    out = {}
    for spot_id, loc in _locations(body, spot_ids).items():
        hourly = loc["hourly"]
        times = _times(hourly)
        wind = [
            WindObs(time=t, speed_ms=s, gust_ms=g, dir_deg=d)
            for t, s, g, d in zip(
                times,
                hourly["wind_speed_10m"],
                hourly.get("wind_gusts_10m", [None] * len(times)),
                hourly.get("wind_direction_10m", [None] * len(times)),
                strict=True,
            )
            if s is not None
        ]
        precip = [
            PrecipObs(time=t, mm=mm)
            for t, mm in zip(times, hourly["precipitation"], strict=True)
            if mm is not None
        ]
        out[spot_id] = (WindSeries(source="openmeteo", obs=wind), precip)
    return out


def parse_marine(body: bytes, spot_ids: list[str]) -> dict[str, WaveSeries]:
    """Per spot: hourly combined sea state (height, peak-ish period, direction)."""
    out = {}
    for spot_id, loc in _locations(body, spot_ids).items():
        hourly = loc["hourly"]
        obs = [
            WaveObs(time=t, hs_m=h, tp_s=p, dp_deg=d)
            for t, h, p, d in zip(
                _times(hourly),
                hourly["wave_height"],
                hourly.get("wave_period", []),
                hourly.get("wave_direction", []),
                strict=True,
            )
            if h is not None
        ]
        out[spot_id] = WaveSeries(
            source="openmeteo", site=f"{loc['latitude']},{loc['longitude']}", obs=obs
        )
    return out


def parse_marine_sst(body: bytes, spot_ids: list[str]) -> dict[str, list[tuple[datetime, float]]]:
    out = {}
    for spot_id, loc in _locations(body, spot_ids).items():
        hourly = loc["hourly"]
        out[spot_id] = [
            (t, v)
            for t, v in zip(_times(hourly), hourly.get("sea_surface_temperature", []), strict=False)
            if v is not None
        ]
    return out
