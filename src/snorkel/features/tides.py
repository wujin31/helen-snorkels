"""Tide helpers: height and direction at any moment from the prediction curve."""

from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timedelta
from typing import Literal

from snorkel.observations import TidePoint

Trend = Literal["incoming", "outgoing", "slack"]


def height_at(points: list[TidePoint], when: datetime) -> float | None:
    """Linear interpolation of predicted height; None outside the curve."""
    if not points or when < points[0].time or when > points[-1].time:
        return None
    times = [p.time for p in points]
    i = bisect_left(times, when)
    if times[i] == when:
        return points[i].height_m
    a, b = points[i - 1], points[i]
    frac = (when - a.time) / (b.time - a.time)
    return a.height_m + frac * (b.height_m - a.height_m)


def trend_at(
    points: list[TidePoint],
    when: datetime,
    slack_m_per_h: float = 0.03,
) -> Trend | None:
    """Rising water is 'incoming'. Near-flat water around a turn is 'slack'."""
    step = timedelta(minutes=30)
    before, after = height_at(points, when - step), height_at(points, when + step)
    if before is None or after is None:
        return None
    rate = after - before  # metres per hour
    if abs(rate) < slack_m_per_h:
        return "slack"
    return "incoming" if rate > 0 else "outgoing"
