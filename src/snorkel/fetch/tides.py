"""NOAA CO-OPS tides and pier observations (station 9410230, La Jolla)."""

from __future__ import annotations

import json
from datetime import timedelta

from snorkel.fetch.base import FetchContext, HttpItem, Item, get_many, unique

COOPS_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
APPLICATION = "snorkel_status"

# product -> extra query params
OBSERVED_PRODUCTS: dict[str, dict[str, str]] = {
    "water_level": {"datum": "MLLW"},
    "water_temperature": {},
    "wind": {},
    "air_temperature": {},
}


def coops_params(station: str, product: str, **extra: str) -> dict[str, str]:
    params = {
        "station": station,
        "product": product,
        "time_zone": "gmt",
        "units": "metric",
        "format": "json",
        "application": APPLICATION,
    }
    params.update(extra)
    return params


def check_coops(body: bytes) -> None:
    """CO-OPS answers errors with HTTP 200 and an {"error": {...}} body."""
    data = json.loads(body)
    if isinstance(data, dict) and "error" in data:
        error = data["error"]
        message = error.get("message", error) if isinstance(error, dict) else error
        raise ValueError(f"CO-OPS error: {message}")


def _stations(ctx: FetchContext) -> list[str]:
    return unique(spot.tide_station for spot in ctx.spots)


def capture_predictions(ctx: FetchContext) -> list[Item]:
    begin = (ctx.now - timedelta(days=int(ctx.params.get("days_back", 1)))).strftime("%Y%m%d")
    end = (ctx.now + timedelta(days=int(ctx.params.get("days_ahead", 3)))).strftime("%Y%m%d")
    items = [
        HttpItem(
            url=COOPS_URL,
            ext="json",
            variant=f"{station}_{label}",
            params=coops_params(
                station,
                "predictions",
                datum="MLLW",
                interval=interval,
                begin_date=begin,
                end_date=end,
            ),
            check=check_coops,
        )
        for station in _stations(ctx)
        for label, interval in (("6min", "6"), ("hilo", "hilo"))
    ]
    return get_many(ctx, items)


def capture_observed(ctx: FetchContext) -> list[Item]:
    hours = str(ctx.params.get("hours", 6))
    items = [
        HttpItem(
            url=COOPS_URL,
            ext="json",
            variant=f"{station}_{product}",
            params=coops_params(station, product, range=hours, **extra),
            check=check_coops,
        )
        for station in _stations(ctx)
        for product, extra in OBSERVED_PRODUCTS.items()
    ]
    return get_many(ctx, items)
