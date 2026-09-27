"""Score every spot for one moment and build the status document."""

from __future__ import annotations

from datetime import datetime, timedelta

from snorkel.models import SourcesConfig, SpotConfig
from snorkel.publish.status import StatusDoc, build_status
from snorkel.score.conditions import Conditions
from snorkel.score.config import ScoringConfig
from snorkel.score.rules import score_spot
from snorkel.sun import LOCAL_TZ, sun_times


def score_all(
    cond: Conditions,
    spots: list[SpotConfig],
    sources: SourcesConfig,
    cfg: ScoringConfig,
) -> StatusDoc:
    today = cond.now.astimezone(LOCAL_TZ).date()
    lat, lon = sources.location.lat, sources.location.lon
    sun_today = sun_times(lat, lon, today)
    sun_tomorrow = sun_times(lat, lon, today + timedelta(days=1))
    statuses = [score_spot(s, cond, cfg, sun_today, sun_tomorrow) for s in spots]
    return build_status(statuses, cond, cfg, sun_today)


def empty_conditions(now: datetime) -> Conditions:
    """What the scorer sees when every source is down: it must still render."""
    return Conditions(now=now)
