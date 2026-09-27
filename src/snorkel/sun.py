"""Sun position, for daylight-gating the cam and later the best-window math."""

from __future__ import annotations

from datetime import datetime

from astral import Observer
from astral.sun import elevation


def sun_elevation(lat: float, lon: float, when: datetime) -> float:
    """Solar elevation in degrees above the horizon (negative at night)."""
    if when.tzinfo is None:
        raise ValueError("when must be timezone-aware")
    return float(elevation(Observer(latitude=lat, longitude=lon), when))
