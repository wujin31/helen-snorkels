"""CDIP waves: buoy realtime spectra and MOP alongshore nowcasts/forecasts.

The archive keeps the full spectral variables (energy density and directional
moments by frequency), not just Hs, because Phase 4 computes near-bottom
orbital velocity from them and archived spectra can't be recomputed later
from summary stats.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from snorkel.fetch.base import (
    FetchContext,
    HttpItem,
    Item,
    ItemError,
    RawSnapshot,
    SkipSource,
    describe_error,
    get_many,
    unique,
)


def subset_recent(ds: Any, cutoff: datetime) -> Any:
    """Slice every `*Time` dimension down to entries at or after `cutoff`.

    CDIP files carry several independent time axes (waveTime, sstTime,
    gpsTime, ...). Each is trimmed separately; variables without a time axis
    (frequencies, station metadata) are kept whole.
    """
    cutoff64 = np.datetime64(cutoff.replace(tzinfo=None), "ns")
    indexers: dict[str, slice] = {}
    for dim in ds.dims:
        name = str(dim)
        if not name.endswith("Time") or name not in ds.variables:
            continue
        times = ds[name].values
        if not np.issubdtype(times.dtype, np.datetime64):
            continue
        recent = np.nonzero(times >= cutoff64)[0]
        indexers[name] = slice(int(recent[0]), None) if len(recent) else slice(0, 0)
    return ds.isel(indexers)


def dataset_subset_bytes(url: str, cutoff: datetime) -> tuple[bytes, dict[str, Any]]:
    """Open a (remote OPeNDAP or local) netCDF, keep recent rows, return netCDF bytes."""
    import xarray as xr

    with xr.open_dataset(url, engine="netcdf4") as ds:
        subset = subset_recent(ds, cutoff).load()
    # Encodings inherited from the server (chunking, fill values, packing)
    # can conflict on write; let xarray pick fresh ones.
    for variable in subset.variables.values():
        variable.encoding = {}
    meta = {name: int(size) for name, size in subset.sizes.items() if str(name).endswith("Time")}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "subset.nc"
        subset.to_netcdf(path, engine="netcdf4")
        return path.read_bytes(), {"rows": meta}


def _capture_subsets(ctx: FetchContext, targets: list[tuple[str, str]]) -> list[Item]:
    cutoff = ctx.now - timedelta(hours=float(ctx.params.get("hours", 3)))
    out: list[Item] = []
    for variant, url in targets:
        try:
            content, meta = dataset_subset_bytes(url, cutoff)
            out.append(RawSnapshot(content=content, ext="nc", url=url, variant=variant, meta=meta))
        except Exception as exc:
            out.append(ItemError(error=describe_error(exc), url=url, variant=variant))
    return out


def _mop_ids(ctx: FetchContext) -> list[str]:
    ids = unique(s.cdip_mop_id for s in ctx.spots if s.cdip_mop_id)
    if not ids:
        raise SkipSource("no spot has a cdip_mop_id yet")
    return [i for i in ids if i]


def capture_buoy(ctx: FetchContext) -> list[Item]:
    dods = str(ctx.require("dods")).rstrip("/")
    buoys = unique(s.cdip_buoy for s in ctx.spots if s.cdip_buoy)
    if not buoys:
        raise SkipSource("no spot has a cdip_buoy")
    targets = [(f"buoy{b}", f"{dods}/cdip/realtime/{b}p1_rt.nc") for b in buoys if b]
    return _capture_subsets(ctx, targets)


def capture_mop_nowcast(ctx: FetchContext) -> list[Item]:
    dods = str(ctx.require("dods")).rstrip("/")
    path = str(ctx.require("mop_path")).strip("/")
    targets = [(mop, f"{dods}/{path}/{mop}_nowcast.nc") for mop in _mop_ids(ctx)]
    return _capture_subsets(ctx, targets)


def capture_mop_forecast(ctx: FetchContext) -> list[Item]:
    fileserver = str(ctx.require("fileserver")).rstrip("/")
    path = str(ctx.require("mop_path")).strip("/")
    items = [
        HttpItem(url=f"{fileserver}/{path}/{mop}_forecast.nc", ext="nc", variant=mop)
        for mop in _mop_ids(ctx)
    ]
    return get_many(ctx, items)
