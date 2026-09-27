"""NOAA CO-OPS datagetter JSON (time_zone=gmt, units=metric)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from snorkel.observations import TideExtreme, TidePoint, WaterTemp, WindObs, WindSeries


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def _float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _rows(body: bytes, key: str) -> list[dict[str, str]]:
    data = json.loads(body)
    if "error" in data:
        raise ValueError(f"CO-OPS error: {data['error']}")
    rows = data.get(key)
    if not isinstance(rows, list):
        raise ValueError(f"CO-OPS response has no '{key}' list")
    return rows


def parse_predictions(body: bytes) -> list[TidePoint]:
    return [
        TidePoint(time=_time(r["t"]), height_m=float(r["v"])) for r in _rows(body, "predictions")
    ]


def parse_extremes(body: bytes) -> list[TideExtreme]:
    return [
        TideExtreme(
            time=_time(r["t"]),
            height_m=float(r["v"]),
            kind="high" if r["type"] == "H" else "low",
        )
        for r in _rows(body, "predictions")
    ]


def parse_wind(body: bytes) -> WindSeries:
    obs = []
    for r in _rows(body, "data"):
        speed = _float(r.get("s"))
        if speed is None:
            continue
        obs.append(
            WindObs(
                time=_time(r["t"]),
                speed_ms=speed,
                gust_ms=_float(r.get("g")),
                dir_deg=_float(r.get("d")),
            )
        )
    return WindSeries(source="coops", obs=obs)


def parse_water_temp(body: bytes) -> WaterTemp:
    valid = [r for r in _rows(body, "data") if _float(r.get("v")) is not None]
    if not valid:
        raise ValueError("no water temperature readings")
    last = valid[-1]
    return WaterTemp(time=_time(last["t"]), temp_c=float(last["v"]), source="coops")
