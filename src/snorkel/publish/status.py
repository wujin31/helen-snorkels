"""status.json: the one document the page renders, answer first."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from snorkel.features.tides import height_at
from snorkel.observations import SourceResult, TideExtreme
from snorkel.score.conditions import Conditions
from snorkel.score.config import DIFFICULTY_ORDER, ScoringConfig
from snorkel.score.models import SpotStatus, TimeWindow
from snorkel.sun import LOCAL_TZ, SunTimes
from snorkel.units import c_to_f, m_to_ft

DISCLAIMER = (
    "Conditions change quickly. Check with the lifeguards on site, and trust your own read "
    "of surge, currents and wildlife once you're there."
)
VERDICT_RANK = {"yes": 0, "maybe": 1, "unknown": 2, "no": 3}

SOURCE_LABELS = {
    "tides": "Tide predictions (NOAA 9410230)",
    "waves": "Waves",
    "wind_obs": "Pier wind (NOAA 9410230)",
    "wind_forecast": "Wind forecast (Open-Meteo)",
    "precip": "Rain (Open-Meteo)",
    "water_temp": "Water temperature",
    "chlorophyll": "Chlorophyll (SCCOOS pier)",
    "turbidity": "Turbidity (SCCOOS pier)",
    "water_quality": "Water quality",
    "alerts": "NWS alerts",
}


class SourceHealth(BaseModel):
    id: str
    label: str
    ok: bool
    stale: bool
    fetched_at: datetime
    valid_at: datetime | None = None
    error: str | None = None


class TideCurvePoint(BaseModel):
    time: datetime
    ft: float


class TideTurn(BaseModel):
    time: datetime
    ft: float
    kind: Literal["high", "low"]


class DayConditions(BaseModel):
    date: str
    sunrise: datetime
    sunset: datetime
    water_temp_f: float | None = None
    water_temp_source: str | None = None
    wetsuit: str | None = None
    turbidity_ntu: float | None = None
    chlorophyll_ug_l: float | None = None
    alerts: list[str] = Field(default_factory=list)
    tide_curve: list[TideCurvePoint] = Field(default_factory=list)
    tide_turns: list[TideTurn] = Field(default_factory=list)


class CamReading(BaseModel):
    """What the pier cam showed at one moment (from the cam model)."""

    time: datetime
    vis_ft: tuple[int, int] | None = None
    pilings_visible: int | None = None
    pilings_total: int | None = None


class CamInfo(BaseModel):
    """The live cam section: where to watch it and when it's worth watching."""

    title: str
    caption: str
    watch_url: str
    info_url: str | None = None
    embed_url: str | None = None  # set only when the player allows this site to frame it
    light: list[TimeWindow] = Field(default_factory=list)  # today and tomorrow
    reading: CamReading | None = None
    readings_today: list[CamReading] = Field(default_factory=list)


class StatusDoc(BaseModel):
    version: int = 1
    generated_at: datetime
    timezone: str = "America/Los_Angeles"
    summary: str
    best_bet: str | None
    spots: list[SpotStatus]
    day: DayConditions
    sources: list[SourceHealth]
    disclaimer: str = DISCLAIMER
    cam: CamInfo | None = None


def short_name(name: str) -> str:
    return name.split(" / ")[0]


def clock(t: datetime) -> str:
    local = t.astimezone(LOCAL_TZ)
    return f"{local.hour % 12 or 12}:{local.minute:02d}"


def window_text(status: SpotStatus) -> str:
    if not status.window:
        return ""
    start, end = status.window.start.astimezone(LOCAL_TZ), status.window.end.astimezone(LOCAL_TZ)
    suffix = "am" if end.hour < 12 else "pm"
    if (start.hour < 12) != (end.hour < 12):
        text = f"{clock(start)} {'am' if start.hour < 12 else 'pm'}–{clock(end)} {suffix}"
    else:
        text = f"{clock(start)}–{clock(end)} {suffix}"
    return f"tomorrow {text}" if status.window_day == "tomorrow" else text


def best_bet(spots: list[SpotStatus], cfg: ScoringConfig) -> SpotStatus | None:
    allowed = DIFFICULTY_ORDER[cfg.preferences.max_difficulty]
    candidates = [s for s in spots if DIFFICULTY_ORDER[s.difficulty] <= allowed] or spots
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda s: (
            VERDICT_RANK[s.verdict],
            -((s.vis_ft[0] + s.vis_ft[1]) / 2 if s.vis_ft else 0),
            s.tier,
        ),
    )


def summarize(spots: list[SpotStatus], best: SpotStatus | None) -> str:
    """One calm sentence for the top of the page. Never says 'safe'."""
    if best is None or best.verdict == "unknown":
        return "Not enough fresh data to call it right now."
    others = [s for s in spots if s.id != best.id and s.tier == 1]
    if best.verdict == "no":
        return f"Not a snorkel day: {best.reason[0].lower()}{best.reason[1:]}."
    when = window_text(best)
    head = (
        f"{short_name(best.name)} looks good"
        if best.verdict == "yes"
        else (f"Maybe {short_name(best.name)}")
    )
    sentence = f"{head} {when}".strip() + "."
    for other in others:
        if other.verdict == "no":
            sentence += f" {short_name(other.name)}: {other.reason[0].lower()}{other.reason[1:]}."
    return sentence


def _health(key: str, result: SourceResult, stale_hours: float, now: datetime) -> SourceHealth:  # type: ignore[type-arg]
    reference = result.valid_at or result.fetched_at
    return SourceHealth(
        id=key,
        label=SOURCE_LABELS.get(key.split(":")[0], key),
        ok=result.ok,
        stale=(not result.ok) or now - reference > timedelta(hours=stale_hours),
        fetched_at=result.fetched_at,
        valid_at=result.valid_at,
        error=result.error,
    )


def source_health(cond: Conditions, cfg: ScoringConfig) -> list[SourceHealth]:
    kinds = {
        "tides": "tides",
        "wind_obs": "wind",
        "water_temp": "water_temp",
        "chlorophyll": "chlorophyll",
        "turbidity": "turbidity",
        "alerts": "alerts",
    }
    out = []
    for key, kind in kinds.items():
        result = getattr(cond, key)
        if result is not None:
            out.append(_health(key, result, cfg.staleness_hours.get(kind, 6), cond.now))
    groups = {
        "waves": (cond.waves, "waves"),
        "wind_forecast": (cond.wind_forecast, "wind"),
        "precip": (cond.precip, "rain"),
        "water_quality": (cond.water_quality, "water_quality"),
    }
    for key, (group, kind) in groups.items():
        for spot_id, result in group.items():
            health = _health(f"{key}:{spot_id}", result, cfg.staleness_hours.get(kind, 6), cond.now)
            health.label = f"{SOURCE_LABELS[key]} · {spot_id}"
            if key == "waves" and result.value is not None:
                health.label = f"Waves ({result.value.source}) · {spot_id}"
            out.append(health)
    return out


def day_conditions(cond: Conditions, cfg: ScoringConfig, sun: SunTimes) -> DayConditions:
    local_day = sun.sunrise.astimezone(LOCAL_TZ).date()
    day = DayConditions(date=local_day.isoformat(), sunrise=sun.sunrise, sunset=sun.sunset)
    if cond.water_temp and cond.water_temp.ok and cond.water_temp.value:
        temp_f = c_to_f(cond.water_temp.value.temp_c)
        day.water_temp_f = round(temp_f, 1)
        day.water_temp_source = cond.water_temp.value.source
        day.wetsuit = cfg.wetsuit(temp_f)
    if cond.turbidity and cond.turbidity.ok and cond.turbidity.value:
        day.turbidity_ntu = cond.turbidity.value.ntu
    if cond.chlorophyll and cond.chlorophyll.ok and cond.chlorophyll.value:
        day.chlorophyll_ug_l = cond.chlorophyll.value.chl_ug_l
    if cond.alerts and cond.alerts.ok and cond.alerts.value:
        day.alerts = sorted({a.event for a in cond.alerts.value})
    tides = cond.tides.value if cond.tides and cond.tides.ok else None
    if tides:
        start = sun.sunrise - timedelta(hours=1.5)
        end = sun.sunset + timedelta(hours=1.5)
        t = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        while t <= end:
            h = height_at(tides.points, t)
            if h is not None:
                day.tide_curve.append(TideCurvePoint(time=t, ft=round(m_to_ft(h), 2)))
            t += timedelta(minutes=15)
        day.tide_turns = [_turn(e) for e in tides.extremes if start <= e.time <= end]
    return day


def _turn(e: TideExtreme) -> TideTurn:
    return TideTurn(time=e.time, ft=round(m_to_ft(e.height_m), 2), kind=e.kind)


def build_status(
    spots: list[SpotStatus],
    cond: Conditions,
    cfg: ScoringConfig,
    sun: SunTimes,
    cam: CamInfo | None = None,
) -> StatusDoc:
    best = best_bet(spots, cfg)
    ranked = sorted(
        spots, key=lambda s: (s.id != (best.id if best else None), VERDICT_RANK[s.verdict], s.tier)
    )
    return StatusDoc(
        generated_at=cond.now,
        summary=summarize(spots, best),
        best_bet=best.id if best and best.verdict in ("yes", "maybe") else None,
        spots=ranked,
        day=day_conditions(cond, cfg, sun),
        sources=source_health(cond, cfg),
        cam=cam,
    )


def history_rows(doc: StatusDoc) -> list[dict[str, object]]:
    """Compact per-spot rows for history.jsonl: the future accuracy record."""
    rows = []
    for s in doc.spots:
        rows.append(
            {
                "t": doc.generated_at.isoformat(),
                "spot": s.id,
                "verdict": s.verdict,
                "confidence": s.confidence,
                "vis_ft": list(s.vis_ft) if s.vis_ft else None,
                "hs_ft": s.conditions.hs_ft,
                "tp_s": s.conditions.tp_s,
                "wave_source": s.conditions.wave_source,
                "orbital_ms": s.conditions.orbital_ms,
                "wind_kt": s.conditions.wind_kt,
                "tide_ft": s.conditions.tide_ft,
                "turbidity_ntu": doc.day.turbidity_ntu,
                "chl_ug_l": doc.day.chlorophyll_ug_l,
                "water_temp_f": doc.day.water_temp_f,
                "gates": s.gates,
                "window": [s.window.start.isoformat(), s.window.end.isoformat()]
                if s.window
                else None,
            }
        )
    return rows
