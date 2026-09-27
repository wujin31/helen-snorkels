"""Score every spot for one moment and build the status document."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from snorkel.models import SourcesConfig, SpotConfig
from snorkel.publish.status import CamInfo, StatusDoc, build_status
from snorkel.score.conditions import Conditions
from snorkel.score.config import ScoringConfig
from snorkel.score.models import TimeWindow
from snorkel.score.rules import score_spot
from snorkel.sun import LOCAL_TZ, light_window, sun_times

CAM_SOURCE = "cam.scripps_pier"


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
    # After the last usable light, the page is about tomorrow morning.
    tail = timedelta(minutes=cfg.preferences.latest_end_before_sunset_min)
    day_sun = sun_tomorrow if cond.now > sun_today.sunset - tail else sun_today
    return build_status(statuses, cond, cfg, day_sun, cam=cam_info(sources, today))


def cam_info(sources: SourcesConfig, today: date) -> CamInfo | None:
    """The page's cam section, from the capture config; None if there's no cam."""
    params = sources.sources.get(CAM_SOURCE)
    if not params or not params.get("watch_url"):
        return None
    lat, lon = sources.location.lat, sources.location.lon
    min_elevation = float(params.get("min_sun_elevation_deg", 2))
    light = [light_window(lat, lon, today + timedelta(days=d), min_elevation) for d in (0, 1)]
    return CamInfo(
        title=params.get("title", "Live cam"),
        caption=params.get("caption", ""),
        watch_url=params["watch_url"],
        info_url=params.get("info_url"),
        embed_url=params.get("site_embed_url"),
        light=[TimeWindow(start=w.sunrise, end=w.sunset) for w in light],
    )


def empty_conditions(now: datetime) -> Conditions:
    """What the scorer sees when every source is down: it must still render."""
    return Conditions(now=now)
