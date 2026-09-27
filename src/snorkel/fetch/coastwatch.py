"""NOAA CoastWatch VIIRS ocean color (Kd490, chlorophyll) near each spot."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from snorkel.fetch.base import FetchContext, HttpItem, Item, get_many


def griddap_url(
    erddap: str,
    dataset: dict[str, Any],
    lat: float,
    lon: float,
    box_deg: float,
) -> str:
    """Latest time step of `dataset['var']` in a small box around (lat, lon)."""
    lat_lo, lat_hi = lat - box_deg, lat + box_deg
    lon_lo, lon_hi = lon - box_deg, lon + box_deg
    lat_sel = (
        f"[({lat_hi:.4f}):({lat_lo:.4f})]"
        if dataset.get("lat_descending")
        else f"[({lat_lo:.4f}):({lat_hi:.4f})]"
    )
    altitude = "[(0.0)]" if dataset.get("altitude") else ""
    query = f"{dataset['var']}[(last)]{altitude}{lat_sel}[({lon_lo:.4f}):({lon_hi:.4f})]"
    return f"{erddap.rstrip('/')}/griddap/{dataset['id']}.nc?{quote(query, safe='():.-_')}"


def capture_viirs(ctx: FetchContext) -> list[Item]:
    erddap = str(ctx.require("erddap"))
    datasets: list[dict[str, Any]] = ctx.require("datasets")
    box = float(ctx.params.get("box_deg", 0.05))
    items = [
        HttpItem(
            url=griddap_url(erddap, dataset, spot.lat, spot.lon, box),
            ext="nc",
            variant=f"{dataset['id']}_{spot.id}",
        )
        for dataset in datasets
        for spot in ctx.spots
    ]
    return get_many(ctx, items)
