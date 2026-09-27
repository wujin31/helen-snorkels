from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from snorkel.fetch.cdip import dataset_subset_bytes


def test_subset_keeps_recent_rows_on_every_time_axis(tmp_path: Path) -> None:
    wave_time = pd.date_range("2026-09-27T00:00", periods=48, freq="30min")
    sst_time = pd.date_range("2026-09-27T00:00", periods=24, freq="60min")
    freq = np.linspace(0.025, 0.58, 64)
    ds = xr.Dataset(
        {
            "waveHs": ("waveTime", np.linspace(0.5, 1.5, 48)),
            "waveEnergyDensity": (("waveTime", "waveFrequency"), np.ones((48, 64))),
            "sstSeaSurfaceTemperature": ("sstTime", np.full(24, 20.5)),
            "waveBandwidth": ("waveFrequency", np.full(64, 0.01)),
            "sourceFilename": ("sourceCount", np.array([b"file%05d.nc" % i for i in range(2000)])),
        },
        coords={"waveTime": wave_time, "sstTime": sst_time, "waveFrequency": freq},
    )
    source = tmp_path / "201p1_rt.nc"
    ds.to_netcdf(source)

    content, meta = dataset_subset_bytes(str(source), datetime(2026, 9, 27, 21, 0, tzinfo=UTC))
    out = tmp_path / "out.nc"
    out.write_bytes(content)
    with xr.open_dataset(out) as sub:
        assert sub.sizes["waveTime"] == 6  # 21:00 .. 23:30
        assert sub.sizes["sstTime"] == 3  # 21:00 .. 23:00
        assert sub.sizes["waveFrequency"] == 64  # spectra kept whole
        assert sub["waveEnergyDensity"].shape == (6, 64)
        assert "sourceFilename" not in sub.variables
    assert meta["rows"] == {"waveTime": 6, "sstTime": 3}
