"""CDIP netCDF (buoy realtime and MOP nowcast): bulk wave parameters."""

from __future__ import annotations

import math
import tempfile
from datetime import UTC
from pathlib import Path
from typing import Literal

import numpy as np

from snorkel.observations import WaveObs, WaveSeries


def parse_waves(content: bytes, source: Literal["mop", "buoy"], site: str) -> WaveSeries:
    import xarray as xr

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "waves.nc"
        path.write_bytes(content)
        with xr.open_dataset(path) as ds:
            if "waveHs" not in ds.variables:
                raise ValueError(f"no waveHs in {sorted(map(str, ds.variables))[:20]}")
            times = ds["waveTime"].values
            hs = ds["waveHs"].values
            tp = ds["waveTp"].values if "waveTp" in ds.variables else np.full(len(hs), np.nan)
            dp = ds["waveDp"].values if "waveDp" in ds.variables else np.full(len(hs), np.nan)
    obs = []
    for t, h, p, d in zip(times, hs, tp, dp, strict=True):
        if not math.isfinite(float(h)):
            continue
        when = np.datetime64(t, "s").astype("datetime64[s]").item().replace(tzinfo=UTC)
        obs.append(
            WaveObs(
                time=when,
                hs_m=float(h),
                tp_s=float(p) if math.isfinite(float(p)) else None,
                dp_deg=float(d) if math.isfinite(float(d)) else None,
            )
        )
    return WaveSeries(source=source, site=site, obs=obs)
