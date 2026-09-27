"""San Diego County water-quality sites (sdbeachinfo.com screen service JSON)."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from snorkel.observations import WaterQuality

Status = Literal["open", "advisory", "closure", "unknown"]

# PriorityMax on each site is its most severe active event. Decoded from the
# page's own counts on 2026-09-27 (78 sites at 1, 8 at 2 = "8 advisories",
# 4 at 4 = "4 closures"); 3 is the page's "warning", treated as an advisory.
PRIORITY_STATUS: dict[int, Status] = {1: "open", 2: "advisory", 3: "advisory", 4: "closure"}


class CountySite(BaseModel):
    id: str
    beach: str
    location: str
    lat: float | None = None
    lon: float | None = None
    priority: int = 0


def parse_sites(body: bytes) -> list[CountySite]:
    data = json.loads(body)
    rows = data["data"]["List"]["List"]
    sites = []
    for row in rows:
        site = row.get("Site", row)
        sites.append(
            CountySite(
                id=str(site["Id"]),
                beach=site.get("BeachName") or "",
                location=site.get("LocationName") or "",
                lat=float(site["Latitude"]) if site.get("Latitude") else None,
                lon=float(site["Longitude"]) if site.get("Longitude") else None,
                priority=int(row.get("PriorityMax", site.get("PriorityMax", 0)) or 0),
            )
        )
    return sites


def status_for(site_ids: list[str], sites: list[CountySite]) -> WaterQuality:
    """Worst status across a spot's sampling sites."""
    by_id = {s.id: s for s in sites}
    missing = [i for i in site_ids if i not in by_id]
    if missing:
        raise ValueError(f"county sites not found: {', '.join(missing)}")
    order = {"closure": 3, "advisory": 2, "unknown": 1, "open": 0}
    worst: WaterQuality | None = None
    for site_id in site_ids:
        site = by_id[site_id]
        status = PRIORITY_STATUS.get(site.priority, "unknown")
        current = WaterQuality(
            status=status,
            station=site_id,
            detail=site.location or site.beach,
        )
        if worst is None or order[current.status] > order[worst.status]:
            worst = current
    assert worst is not None
    return worst
