"""Pydantic data contracts shared across the pipeline.

Internal units are SI and timestamps are timezone-aware UTC. Conversion to
ft / °F / kt and America/Los_Angeles happens only at display time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Difficulty = Literal["easy", "moderate", "advanced"]
Access = Literal["shore", "strenuous", "boat"]


class ExposureDeg(BaseModel):
    """Swell directions (degrees true, coming-from) that reach or miss a spot."""

    exposed: tuple[float, float]
    sheltered: tuple[float, float] | None = None


class Thresholds(BaseModel):
    max_hs_ft: float
    max_wind_kt: float


class TideRules(BaseModel):
    prefer: Literal["incoming", "outgoing", "any"] = "any"


class SeasonalClosure(BaseModel):
    start: str = Field(pattern=r"^\d{2}-\d{2}$", description="MM-DD, inclusive")
    end: str = Field(pattern=r"^\d{2}-\d{2}$", description="MM-DD, inclusive")
    reason: str


class SpotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    lat: float
    lon: float
    tier: int
    difficulty: Difficulty
    access: Access
    bottom_depth_m: float
    shore_normal_deg: float
    cdip_mop_id: str | None = None
    cdip_buoy: str | None = None
    tide_station: str
    water_quality_ids: list[str] = Field(default_factory=list)
    exposure_deg: ExposureDeg
    thresholds: Thresholds
    tide_rules: TideRules = Field(default_factory=TideRules)
    min_tide_ft: float | None = None
    seasonal_closures: list[SeasonalClosure] = Field(default_factory=list)
    near_pier: bool = False  # beside Scripps Pier: its turbidity sensor counts for more here
    area: str = "La Jolla"  # groups spots on the page
    wave_factor: float = Field(default=1.0, gt=0, le=1)
    """Share of the open-coast wave height that reaches a sheltered spot (bays, harbors)."""
    notes: str = ""


class Location(BaseModel):
    lat: float
    lon: float


class SourcesConfig(BaseModel):
    """`config/sources.yaml`: archiver cadence and per-source parameters."""

    location: Location
    sources: dict[str, dict[str, Any]]

    @field_validator("sources")
    @classmethod
    def _every_source_has_cadence(cls, v: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        for source_id, params in v.items():
            every = params.get("every_minutes")
            if not isinstance(every, int) or every <= 0:
                raise ValueError(f"{source_id}: every_minutes must be a positive integer")
        return v


CaptureStatus = Literal["ok", "error", "skipped"]


class CaptureRecord(BaseModel):
    """One manifest row: the outcome of capturing one item from one source."""

    source: str
    variant: str | None = None
    run_at: datetime
    status: CaptureStatus
    url: str | None = None
    key: str | None = None
    bytes: int | None = None
    sha256: str | None = None
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
