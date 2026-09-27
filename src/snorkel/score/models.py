"""Scorer output: the per-spot verdicts that become status.json."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["yes", "maybe", "no", "unknown"]
Confidence = Literal["high", "medium", "low"]
Effect = Literal["+", "-", "~"]


class Factor(BaseModel):
    label: str
    effect: Effect
    detail: str = ""


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class HourScore(BaseModel):
    time: datetime
    score: float
    tide_ft: float | None = None
    tide_trend: str | None = None
    wind_kt: float | None = None


class SpotConditions(BaseModel):
    hs_ft: float | None = None
    tp_s: float | None = None
    swell_dir_deg: float | None = None
    wave_source: str | None = None
    orbital_ms: float | None = None
    wind_kt: float | None = None
    gust_kt: float | None = None
    wind_dir_deg: float | None = None
    wind_onshore: bool | None = None
    tide_ft: float | None = None
    tide_trend: str | None = None


class SpotStatus(BaseModel):
    id: str
    name: str
    tier: int
    difficulty: str
    verdict: Verdict
    confidence: Confidence
    vis_ft: tuple[int, int] | None = None
    reason: str
    window: TimeWindow | None = None
    window_day: Literal["today", "tomorrow"] | None = None
    gates: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    factors: list[Factor] = Field(default_factory=list)
    conditions: SpotConditions = Field(default_factory=SpotConditions)
    hourly: list[HourScore] = Field(default_factory=list)
    shore_normal_deg: float
    has_cam: bool = False
