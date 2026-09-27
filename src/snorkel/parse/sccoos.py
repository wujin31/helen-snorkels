"""SCCOOS Scripps Pier automated shore station (ERDDAP tabledap CSV)."""

from __future__ import annotations

import csv
import io
import math
from datetime import datetime

from snorkel.observations import Chlorophyll, Turbidity, WaterTemp

# IOOS QARTOD aggregate flags: 1 pass, 2 not evaluated, 3 suspect, 4 fail, 9 missing.
GOOD_FLAGS = {"1", "2"}

TEMPERATURE = "sea_water_temperature_ctd"
CHLOROPHYLL = (
    "mass_concentration_of_chlorophyll_in_sea_water_eco",
    "mass_concentration_of_chlorophyll_in_sea_water_ctd",
)
TURBIDITY = "sea_water_turbidity_eco"


def _latest(rows: list[dict[str, str]], column: str) -> tuple[datetime, float] | None:
    for row in reversed(rows):
        raw = row.get(column, "")
        flag = row.get(f"{column}_qc_agg", "2")
        try:
            value = float(raw)
        except ValueError:
            continue
        if math.isnan(value) or flag not in GOOD_FLAGS:
            continue
        return datetime.fromisoformat(row["time"].replace("Z", "+00:00")), value
    return None


def parse_pier(
    body: bytes,
) -> tuple[WaterTemp | None, Chlorophyll | None, Turbidity | None]:
    lines = body.decode("utf-8").splitlines()
    if len(lines) < 3 or not lines[0].startswith("time,"):
        raise ValueError("unexpected ERDDAP CSV")
    # Line 2 holds units; data starts on line 3.
    rows = list(csv.DictReader(io.StringIO("\n".join([lines[0], *lines[2:]]))))
    temp = _latest(rows, TEMPERATURE)
    chl = next((c for c in (_latest(rows, col) for col in CHLOROPHYLL) if c), None)
    turb = _latest(rows, TURBIDITY)
    return (
        WaterTemp(time=temp[0], temp_c=temp[1], source="sccoos") if temp else None,
        Chlorophyll(time=chl[0], chl_ug_l=chl[1]) if chl else None,
        Turbidity(time=turb[0], ntu=turb[1]) if turb else None,
    )
