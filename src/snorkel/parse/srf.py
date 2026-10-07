"""NWS Surf Zone Forecast (SRF) text, from api.weather.gov/products/{id}.

The product is plain text: one segment per coastal zone, each with periods
like `.TODAY...` (or, in afternoon issues, `.THIS AFTERNOON THROUGH WEDNESDAY...`)
holding dotted key/value lines:

    Rip Current Risk*.............Moderate.
    Surf Height...................2 to 4 feet. Sets to 5 feet.
    Water Temperature.............68 to 72 degrees.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from snorkel.observations import SurfForecast, SurfPeriod
from snorkel.sun import LOCAL_TZ

SAN_DIEGO_ZONE = "San Diego County Coastal Areas"
WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

PERIOD_RE = re.compile(r"^\.([A-Z][A-Z ]*?)\.\.\.\s*$")
FIELD_RE = re.compile(r"^([A-Za-z ]+?)\*?\.{2,}\s*(.*)$")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _period_day(name: str, issued_local: date) -> date | None:
    first = name.split()[0]
    if first in {"TODAY", "TONIGHT", "THIS", "REST"}:
        return issued_local
    if first in WEEKDAYS:
        ahead = (WEEKDAYS.index(first) - issued_local.weekday()) % 7
        return issued_local + timedelta(days=ahead or 7)
    return None


def _period_days(name: str, issued_local: date) -> tuple[date, date | None] | None:
    """First day and, for "X THROUGH Y" periods, the last day the period covers."""
    start, _, end = name.partition(" THROUGH ")
    first = _period_day(start, issued_local)
    if first is None:
        return None
    last = _period_day(end, issued_local) if end else None
    return first, last if last and last > first else None


def _range(text: str) -> tuple[float, float] | None:
    """'2 to 4 feet' -> (2, 4); '1 foot or less' -> (0, 1); '3 feet' -> (3, 3)."""
    lowered = text.lower()
    nums = [float(n) for n in NUMBER_RE.findall(lowered.split("sets")[0])]
    if not nums:
        return None
    if "or less" in lowered or "less than" in lowered:
        return 0.0, nums[0]
    return (nums[0], nums[1]) if len(nums) > 1 else (nums[0], nums[0])


def parse_srf(body: bytes, zone: str = SAN_DIEGO_ZONE) -> SurfForecast:
    data = json.loads(body)
    text = data.get("productText")
    if not isinstance(text, str):
        raise ValueError("SRF product without productText")
    issued = datetime.fromisoformat(data["issuanceTime"])
    issued_local = issued.astimezone(LOCAL_TZ).date()
    segment = next((s for s in text.split("$$") if f"\n{zone}-" in s), None)
    if segment is None:
        raise ValueError(f"no '{zone}' segment in the SRF")
    periods: list[SurfPeriod] = []
    current: SurfPeriod | None = None
    for raw in segment.splitlines():
        line = raw.strip()
        if line.startswith("&&"):
            break
        head = PERIOD_RE.match(line)
        if head:
            days = _period_days(head.group(1), issued_local)
            current = (
                SurfPeriod(name=head.group(1).title(), day=days[0], last_day=days[1])
                if days
                else None
            )
            if current:
                periods.append(current)
            continue
        found = FIELD_RE.match(line)
        if not current or not found:
            continue
        key, value = found.group(1).strip().lower(), found.group(2).strip().rstrip(".")
        if key == "rip current risk" and value:
            current.rip_risk = value.split()[0].title()
        elif key == "surf height" and value:
            current.surf_ft = _range(value)
            sets = re.search(r"sets to (\d+(?:\.\d+)?)", value.lower())
            current.sets_ft = float(sets.group(1)) if sets else None
        elif key == "water temperature" and value:
            current.water_temp_f = _range(value)
        elif key == "remarks" and value:
            current.remarks = value
    return SurfForecast(issued=issued, zone=zone, periods=periods)
