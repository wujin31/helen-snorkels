"""NDBC realtime2 standard meteorological text files."""

from __future__ import annotations

from datetime import UTC, datetime

from snorkel.observations import WindObs, WindSeries


def _value(token: str) -> float | None:
    return None if token == "MM" else float(token)


def parse_stdmet_wind(text: str) -> WindSeries:
    header: list[str] | None = None
    obs: list[WindObs] = []
    for line in text.splitlines():
        if line.startswith("#"):
            header = header or line.lstrip("#").split()
            continue
        if header is None:
            raise ValueError("NDBC file without a header")
        row = dict(zip(header, line.split(), strict=False))
        try:
            when = datetime(
                int(row["YY"]),
                int(row["MM"]),
                int(row["DD"]),
                int(row["hh"]),
                int(row["mm"]),
                tzinfo=UTC,
            )
        except (KeyError, ValueError):
            continue
        speed = _value(row.get("WSPD", "MM"))
        if speed is None:
            continue
        obs.append(
            WindObs(
                time=when,
                speed_ms=speed,
                gust_ms=_value(row.get("GST", "MM")),
                dir_deg=_value(row.get("WDIR", "MM")),
            )
        )
    return WindSeries(source="ndbc", obs=sorted(obs, key=lambda o: o.time))
