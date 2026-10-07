"""Sunrise and sunset, for the best-window math."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sun

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


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
