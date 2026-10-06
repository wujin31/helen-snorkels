#!/usr/bin/env bash
# Does Sentinel-2, corrected against offshore water in the same image, track
# the Scripps Pier turbidity sensor? Text only.
set -u
uv run python - <<'PY'
import io, time, statistics
import httpx
import numpy as np

PC = "https://planetarycomputer.microsoft.com/api"
c = httpx.Client(timeout=60, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"})
body = {"collections": ["sentinel-2-l2a"], "intersects": {"type": "Point", "coordinates": [-117.2571, 32.8666]},
        "datetime": "2026-07-01T00:00:00Z/2026-10-07T00:00:00Z", "limit": 60,
        "sortby": [{"field": "datetime", "direction": "desc"}]}
items = [it for it in c.post(f"{PC}/stac/v1/search", json=body).json()["features"]
         if (it["properties"].get("eo:cloud_cover") or 100) < 30]
print(len(items), "items under 30% cloud since Jul 1")

def crop(item, asset, lon, lat, d=0.0015, size=30):
    for attempt in range(3):
        r = c.get(f"{PC}/data/v1/item/bbox/{lon-d},{lat-d},{lon+d},{lat+d}/{size}x{size}.npy",
                  params={"collection": "sentinel-2-l2a", "item": item["id"], "assets": asset})
        if r.status_code == 200 and r.content[:6] == b"\x93NUMPY":
            return np.load(io.BytesIO(r.content))[0].astype(float)
        time.sleep(2)
    return None

def rho(item, lon, lat):
    b4, b8, scl = (crop(item, a, lon, lat) for a in ("B04", "B08", "SCL"))
    if b4 is None or b8 is None or scl is None:
        return None, 0
    r4, r8 = (b4 - 1000) / 1e4, (b8 - 1000) / 1e4
    ok = (scl == 6) & (r8 < 0.02) & (r8 > -0.05)
    return (float(np.median(r4[ok])) if ok.sum() >= 150 else None), int(ok.sum())

# Pier turbidity (ERDDAP) around each overpass
def pier_ntu(t):
    start = t.replace("Z", "")[:16]
    url = ("https://erddap.cencoos.org/erddap/tabledap/scripps-pier-automated-shore-sta-1.csv"
           f"?time,sea_water_turbidity_eco,sea_water_turbidity_eco_qc_agg&time>={start[:11]}17:00:00Z&time<={start[:11]}20:00:00Z")
    r = c.get(url)
    vals = []
    for line in r.text.splitlines()[2:]:
        parts = line.split(",")
        try:
            v, q = float(parts[1]), parts[2]
        except (ValueError, IndexError):
            continue
        if q in ("1", "2") and v == v:
            vals.append(v)
    return statistics.median(vals) if vals else None

points = {"pier": (-117.2571, 32.8655), "offshore": (-117.3300, 32.8550), "cove": (-117.27228, 32.85196),
          "marine-room": (-117.2620, 32.8545), "swamis": (-117.2960, 33.0350), "sunset": (-117.2640, 32.7190)}
print(f"{'time':17} {'pier NTU':>8} | " + " ".join(f"{k:>11}" for k in points) + " | pier-offshore")
seen = set()
for it in items:
    day = it["properties"]["datetime"][:10]
    if day in seen:
        continue
    seen.add(day)
    vals = {k: rho(it, *p) for k, p in points.items()}
    ntu = pier_ntu(it["properties"]["datetime"])
    cells = " ".join(f"{(v[0] if v[0] is not None else float('nan')):11.4f}" for v in vals.values())
    diff = (vals["pier"][0] - vals["offshore"][0]) if vals["pier"][0] is not None and vals["offshore"][0] is not None else float("nan")
    print(f"{it['properties']['datetime'][:16]} {ntu if ntu is not None else float('nan'):8.2f} | {cells} | {diff:.4f}")
PY
