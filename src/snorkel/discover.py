"""Dev-time discovery helpers: finding station IDs and hidden data endpoints.

Not used by the pipeline. Run them where the data hosts are reachable (a
GitHub runner via the probe workflow, or a dev machine).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from snorkel.http import get_with_retry, user_agent

THREDDS = "https://thredds.cdip.ucsd.edu/thredds"
MOP_PATH = "cdip/model/MOP_alongshore"


@dataclass
class MopSite:
    id: str
    lat: float
    lon: float
    meta: dict[str, Any]

    def distance_km(self, lat: float, lon: float) -> float:
        return haversine_km(self.lat, self.lon, lat, lon)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def list_mop_ids(client: httpx.Client, prefix: str = "D") -> list[str]:
    """MOP ids with a nowcast file, e.g. D0001..D1210 for San Diego County."""
    xml = get_with_retry(client, f"{THREDDS}/catalog/{MOP_PATH}/catalog.xml").text
    return sorted(set(re.findall(rf"({prefix}\d{{4}})_nowcast\.nc", xml)))


def read_mop_site(mop_id: str) -> MopSite:
    import xarray as xr

    url = f"{THREDDS}/dodsC/{MOP_PATH}/{mop_id}_nowcast.nc"
    with xr.open_dataset(url, engine="netcdf4", decode_times=False) as ds:
        meta: dict[str, Any] = {}
        for name in ds.variables:
            var = ds[name]
            if str(name).startswith("meta") and var.size == 1:
                value = var.values.item()
                meta[str(name)] = value.decode() if isinstance(value, bytes) else value
        for key, value in ds.attrs.items():
            if key.startswith(("geospatial_", "title", "summary")):
                meta[key] = value
    lat = meta.get("metaLatitude", meta.get("geospatial_lat_min"))
    lon = meta.get("metaLongitude", meta.get("geospatial_lon_min"))
    if lat is None or lon is None:
        raise ValueError(f"{mop_id}: no latitude/longitude in {sorted(meta)}")
    return MopSite(id=mop_id, lat=float(lat), lon=float(lon), meta=meta)


def nearest_mops(
    lat: float,
    lon: float,
    ids: list[str],
    locate: Callable[[str], MopSite],
    *,
    window: int = 20,
    count: int = 5,
) -> list[MopSite]:
    """Bisect on latitude (MOPs run roughly south to north), then scan nearby."""
    cache: dict[int, MopSite] = {}

    def site(i: int) -> MopSite:
        if i not in cache:
            cache[i] = locate(ids[i])
        return cache[i]

    lo, hi = 0, len(ids) - 1
    while hi - lo > window:
        mid = (lo + hi) // 2
        if site(mid).lat < lat:
            lo = mid
        else:
            hi = mid
    start, stop = max(0, lo - window), min(len(ids), hi + window + 1)
    candidates = []
    for i in range(start, stop):
        try:
            candidates.append(site(i))
        except Exception:
            continue
    return sorted(candidates, key=lambda s: s.distance_km(lat, lon))[:count]


def sniff_requests(page_url: str, wait_s: float = 20) -> list[tuple[str, str, str]]:
    """Load a page headlessly; return (resource type, method, url) for every request.

    Finds the JSON/API or stream URLs a JavaScript-heavy page loads its data from.
    """
    from playwright.sync_api import sync_playwright  # pyright: ignore[reportMissingImports]

    seen: list[tuple[str, str, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"],
        )
        try:
            page = browser.new_page(user_agent=user_agent())
            page.on("request", lambda r: seen.append((r.resource_type, r.method, r.url)))
            page.goto(page_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(wait_s * 1000)
        finally:
            browser.close()
    return seen
