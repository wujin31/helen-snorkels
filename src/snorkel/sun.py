"""Sun position, for daylight-gating the cam and later the best-window math."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from astral import Observer, SunDirection
from astral.sun import elevation, sun, time_at_elevation

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


def light_window(lat: float, lon: float, day: date, min_elevation_deg: float) -> SunTimes:
    """When the sun is at least `min_elevation_deg` up on a local day (UTC).

    The underwater cam shows nothing useful in twilight, so this is "cam light",
    a little inside sunrise and sunset.
    """
    observer = Observer(latitude=lat, longitude=lon)
    rise = time_at_elevation(observer, min_elevation_deg, day, SunDirection.RISING, LOCAL_TZ)
    fall = time_at_elevation(observer, min_elevation_deg, day, SunDirection.SETTING, LOCAL_TZ)
    return SunTimes(sunrise=rise.astimezone(UTC), sunset=fall.astimezone(UTC))
