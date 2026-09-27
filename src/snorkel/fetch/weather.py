"""Wind, rain and weather: NDBC pier obs, Open-Meteo and the NWS API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from snorkel.fetch.base import (
    FetchContext,
    HttpItem,
    Item,
    ItemError,
    describe_error,
    get_many,
    slug,
)
from snorkel.http import get_with_retry

NWS_URL = "https://api.weather.gov"
GEOJSON = {"Accept": "application/geo+json"}

OPENMETEO_FORECAST_HOURLY = [
    "temperature_2m",
    "precipitation",
    "rain",
    "cloud_cover",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]
OPENMETEO_MARINE_HOURLY = [
    "wave_height",
    "wave_direction",
    "wave_period",
    "wind_wave_height",
    "wind_wave_direction",
    "wind_wave_period",
    "swell_wave_height",
    "swell_wave_direction",
    "swell_wave_period",
    "swell_wave_peak_period",
    "sea_surface_temperature",
    "ocean_current_velocity",
    "ocean_current_direction",
]


def trim_ndbc(text: str, now: datetime, keep_hours: float) -> str:
    """Keep the header and only rows newer than `keep_hours`.

    NDBC realtime2 files hold 45 days of 6-minute rows; archiving the whole
    file every hour would be ~99% duplicates.
    """
    cutoff = now - timedelta(hours=keep_hours)
    kept: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            kept.append(line)
            continue
        parts = line.split()
        try:
            year, month, day, hour, minute = (int(p) for p in parts[:5])
            stamp = datetime(year, month, day, hour, minute, tzinfo=UTC)
        except (ValueError, IndexError):
            continue
        if stamp >= cutoff:
            kept.append(line)
    return "\n".join(kept) + "\n"


def capture_ndbc(ctx: FetchContext) -> list[Item]:
    url = ctx.require("url")
    keep_hours = float(ctx.params.get("keep_hours", 6))
    station = url.rstrip("/").rsplit("/", 1)[-1].split(".")[0]
    return get_many(
        ctx,
        [
            HttpItem(
                url=url,
                ext="txt",
                variant=station,
                transform=lambda body: trim_ndbc(
                    body.decode("utf-8", errors="replace"), ctx.now, keep_hours
                ).encode(),
            )
        ],
    )


def _openmeteo_params(ctx: FetchContext, hourly: list[str]) -> dict[str, Any]:
    # One request covers every spot: Open-Meteo takes comma-separated coordinates.
    return {
        "latitude": ",".join(f"{s.lat:.4f}" for s in ctx.spots),
        "longitude": ",".join(f"{s.lon:.4f}" for s in ctx.spots),
        "hourly": ",".join(hourly),
        "past_days": int(ctx.params.get("past_days", 3)),
        "forecast_days": int(ctx.params.get("forecast_days", 3)),
        "timezone": "GMT",
    }


def capture_openmeteo_forecast(ctx: FetchContext) -> list[Item]:
    params = _openmeteo_params(ctx, OPENMETEO_FORECAST_HOURLY)
    params["wind_speed_unit"] = "ms"
    item = HttpItem(
        url=ctx.require("url"),
        ext="json",
        params=params,
        meta={"spots": [s.id for s in ctx.spots]},
    )
    return get_many(ctx, [item])


def capture_openmeteo_marine(ctx: FetchContext) -> list[Item]:
    item = HttpItem(
        url=ctx.require("url"),
        ext="json",
        params=_openmeteo_params(ctx, OPENMETEO_MARINE_HOURLY),
        meta={"spots": [s.id for s in ctx.spots]},
    )
    return get_many(ctx, [item])


def _points(ctx: FetchContext) -> list[tuple[float, float]]:
    return [(float(lat), float(lon)) for lat, lon in ctx.require("points")]


def capture_nws_grid(ctx: FetchContext) -> list[Item]:
    out: list[Item] = []
    seen: set[str] = set()
    for lat, lon in _points(ctx):
        points_url = f"{NWS_URL}/points/{lat:.4f},{lon:.4f}"
        try:
            response = get_with_retry(ctx.client, points_url, headers=GEOJSON, sleep=ctx.sleep)
            grid_url = str(response.json()["properties"]["forecastGridData"])
        except Exception as exc:
            out.append(ItemError(error=describe_error(exc), url=points_url))
            continue
        if grid_url in seen:
            continue
        seen.add(grid_url)
        variant = slug(grid_url.split("/gridpoints/")[-1])
        out += get_many(ctx, [HttpItem(url=grid_url, ext="json", variant=variant, headers=GEOJSON)])
    return out


def capture_nws_alerts(ctx: FetchContext) -> list[Item]:
    items = [
        HttpItem(
            url=f"{NWS_URL}/alerts/active",
            ext="json",
            variant=slug(f"{lat:.3f}_{lon:.3f}"),
            params={"point": f"{lat:.4f},{lon:.4f}"},
            headers=GEOJSON,
        )
        for lat, lon in _points(ctx)
    ]
    return get_many(ctx, items)
