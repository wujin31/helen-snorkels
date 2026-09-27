"""Normalized observations: what parsers produce and the scorer consumes.

SI units, timezone-aware UTC datetimes. Every source result says when it was
fetched and whether it worked, so the page can show what's stale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SourceResult(BaseModel, Generic[T]):
    source: str
    ok: bool
    fetched_at: datetime
    value: T | None = None
    error: str | None = None
    valid_at: datetime | None = None
    """Timestamp of the newest data point, for staleness."""


class TidePoint(BaseModel):
    time: datetime
    height_m: float


class TideExtreme(BaseModel):
    time: datetime
    height_m: float
    kind: Literal["high", "low"]


class Tides(BaseModel):
    station: str
    points: list[TidePoint]
    """Predictions, MLLW, typically every 6 minutes."""
    extremes: list[TideExtreme] = Field(default_factory=list)


class WaveObs(BaseModel):
    time: datetime
    hs_m: float
    tp_s: float | None = None
    dp_deg: float | None = None
    """Peak direction, degrees true, coming from."""


class WaveSeries(BaseModel):
    source: Literal["mop", "buoy", "openmeteo"]
    site: str
    obs: list[WaveObs]


class WindObs(BaseModel):
    time: datetime
    speed_ms: float
    gust_ms: float | None = None
    dir_deg: float | None = None
    """Degrees true, coming from."""


class WindSeries(BaseModel):
    source: str
    obs: list[WindObs]


class WaterTemp(BaseModel):
    time: datetime
    temp_c: float
    source: str


class Chlorophyll(BaseModel):
    time: datetime
    chl_ug_l: float


class PrecipObs(BaseModel):
    time: datetime
    mm: float


class WaterQuality(BaseModel):
    status: Literal["open", "advisory", "closure", "unknown"]
    station: str
    since: datetime | None = None
    detail: str = ""


class Alert(BaseModel):
    event: str
    headline: str = ""
    onset: datetime | None = None
    ends: datetime | None = None
