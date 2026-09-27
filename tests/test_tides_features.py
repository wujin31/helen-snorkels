from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from snorkel.features.tides import height_at, trend_at
from snorkel.observations import TidePoint

START = datetime(2026, 9, 27, 0, tzinfo=UTC)


def semidiurnal(hours: float = 30) -> list[TidePoint]:
    """Idealized M2 tide: 1 m amplitude around 1 m, period 12.42 h, 6-min steps."""
    points = []
    for i in range(int(hours * 10) + 1):
        t = START + timedelta(minutes=6 * i)
        h = 1 + math.sin(2 * math.pi * (i * 0.1) / 12.42)
        points.append(TidePoint(time=t, height_m=h))
    return points


def test_height_interpolates_and_bounds() -> None:
    points = semidiurnal()
    assert height_at(points, START) == pytest.approx(1.0)
    assert height_at(points, START + timedelta(minutes=3)) == pytest.approx(
        (points[0].height_m + points[1].height_m) / 2
    )
    assert height_at(points, START - timedelta(minutes=1)) is None
    assert height_at([], START) is None


def test_trend() -> None:
    points = semidiurnal()
    assert trend_at(points, START + timedelta(hours=1)) == "incoming"
    assert trend_at(points, START + timedelta(hours=6)) == "outgoing"
    assert trend_at(points, START + timedelta(hours=12.42 / 4)) == "slack"  # high water
    assert trend_at(points, START) is None  # needs 30 min either side
