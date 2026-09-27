"""api.weather.gov active alerts (GeoJSON)."""

from __future__ import annotations

import json
from datetime import datetime

from snorkel.observations import Alert


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def parse_alerts(body: bytes) -> list[Alert]:
    data = json.loads(body)
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError("NWS alerts response without features")
    alerts = []
    for feature in features:
        props = feature.get("properties", {})
        alerts.append(
            Alert(
                event=props.get("event", ""),
                headline=props.get("headline") or "",
                onset=_time(props.get("onset") or props.get("effective")),
                ends=_time(props.get("ends") or props.get("expires")),
            )
        )
    return alerts


def active(alerts: list[Alert], now: datetime) -> list[Alert]:
    """Alerts in effect now (an onset in the future doesn't count yet)."""
    return [
        a
        for a in alerts
        if (a.onset is None or a.onset <= now) and (a.ends is None or a.ends >= now)
    ]
