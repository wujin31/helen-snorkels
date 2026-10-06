"""`config/scoring.yaml`: every tunable in the v0 rules, validated."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from snorkel.config import config_dir
from snorkel.models import Difficulty

DIFFICULTY_ORDER: dict[str, int] = {"easy": 0, "moderate": 1, "advanced": 2}


class Preferences(BaseModel):
    min_vis_ft: float
    max_difficulty: Difficulty
    earliest_local: str
    latest_end_before_sunset_min: int


class Gates(BaseModel):
    rain_mm_24h: float
    rain_advisory_hours: float
    hazard_alerts: list[str]
    caution_alerts: list[str]
    comfortable_fraction: float


class VisibilityConfig(BaseModel):
    base_ft: float
    half_life_h: float
    orbital_ft_per_ms: float
    chl_threshold_ug_l: float
    chl_ft_per_ug_l: float
    chl_max_penalty_ft: float
    rain_recent_days: float
    rain_recent_penalty_ft: float
    wind_threshold_kt: float
    wind_ft_per_kt: float
    min_ft: float
    max_ft: float
    spread_fraction: float


class TurbidityConfig(BaseModel):
    vis_ft_at_1_ntu: float
    exponent: float
    weight_near_pier: float
    weight_elsewhere: float
    min_valid_ntu: float = 0.15

    def vis_ft(self, ntu: float) -> float:
        return self.vis_ft_at_1_ntu / max(ntu, 0.05) ** self.exponent


class WindowConfig(BaseModel):
    incoming_bonus: float
    slack_high_bonus: float
    outgoing_penalty: float
    below_min_tide_penalty: float
    wind_weight: float
    slot_minutes: int
    min_minutes: int
    max_minutes: int


class ScoringConfig(BaseModel):
    preferences: Preferences
    staleness_hours: dict[str, float]
    gates: Gates
    visibility: VisibilityConfig
    turbidity: TurbidityConfig
    window: WindowConfig
    wetsuit_f: list[tuple[float, str]]

    def wetsuit(self, temp_f: float) -> str:
        for lower, suggestion in sorted(self.wetsuit_f, reverse=True):
            if temp_f >= lower:
                return suggestion
        return self.wetsuit_f[-1][1]


def load_scoring(path: Path | None = None) -> ScoringConfig:
    path = path or config_dir() / "scoring.yaml"
    return ScoringConfig.model_validate(yaml.safe_load(path.read_text()))
