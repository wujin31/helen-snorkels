"""Sun position and times, for daylight gating and the best-window math."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import elevation, sun

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def sun_elevation(lat: float, lon: float, when: datetime) -> float:
    """Solar elevation in degrees above the horizon (negative at night)."""
    if when.tzinfo is None:
        raise ValueError("when must be timezone-aware")
    return float(elevation(Observer(latitude=lat, longitude=lon), when))


@dataclass(frozen=True)
class SunTimes:
    sunrise: datetime
    sunset: datetime


def sun_times(lat: float, lon: float, day: date) -> SunTimes:
    """Sunrise and sunset (UTC) for a local calendar day in La Jolla."""
    times = sun(Observer(latitude=lat, longitude=lon), date=day, tzinfo=LOCAL_TZ)
    return SunTimes(
        sunrise=times["sunrise"].astimezone(UTC), sunset=times["sunset"].astimezone(UTC)
    )
