#!/usr/bin/env bash
# Can we read Sentinel-2 water reflectance off La Jolla from Planetary Computer?
# Text only: item list, crop shapes, pixel statistics.
set -u
uv run python - <<'PY'
import io, json, time
import httpx
import numpy as np

PC = "https://planetarycomputer.microsoft.com/api"
UA = {"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"}
c = httpx.Client(timeout=60, headers=UA, follow_redirects=True)

body = {
    "collections": ["sentinel-2-l2a"],
    "intersects": {"type": "Point", "coordinates": [-117.2571, 32.8666]},
    "datetime": "2026-09-15T00:00:00Z/2026-10-07T00:00:00Z",
    "limit": 20,
    "sortby": [{"field": "datetime", "direction": "desc"}],
}
r = c.post(f"{PC}/stac/v1/search", json=body)
print("search", r.status_code)
items = r.json().get("features", [])
for it in items:
    p = it["properties"]
    print(f"  {it['id']}  {p['datetime'][:16]}  cloud {p.get('eo:cloud_cover')}  tile {p.get('s2:mgrs_tile')}")
clear = [it for it in items if (it["properties"].get("eo:cloud_cover") or 100) < 40]
if not clear:
    raise SystemExit("no clear items")
item = clear[0]
print("\nusing", item["id"], item["properties"]["datetime"])

# points: (name, lon, lat) offshore of each spot (CDIP MOP 10 m depth points)
points = [("scripps-pier", -117.2571, 32.8666), ("cove D0482", -117.27228, 32.85196),
          ("marine-room D0496", -117.2620, 32.8545), ("swamis D0708", -117.2960, 33.0350)]
d = 0.0015  # ~150 m half-width
for asset in ("B04", "B03", "SCL"):
    for name, lon, lat in points[:2]:
        for url in (
            f"{PC}/data/v1/item/bbox/{lon-d},{lat-d},{lon+d},{lat+d}.npy",
            f"{PC}/data/v1/item/bbox/{lon-d},{lat-d},{lon+d},{lat+d}/30x30.npy",
        ):
            rr = c.get(url, params={"collection": "sentinel-2-l2a", "item": item["id"], "assets": asset})
            info = f"{rr.status_code} {rr.headers.get('content-type')} {len(rr.content)} B"
            if rr.status_code == 200 and rr.content[:6] == b"\x93NUMPY":
                arr = np.load(io.BytesIO(rr.content))
                info += f" shape {arr.shape} dtype {arr.dtype} min {arr.min()} median {np.median(arr[0])} max {arr.max()}"
            else:
                info += " " + rr.text[:200].replace("\n", " ")
            print(f"  {asset} {name} {url.rsplit('/',1)[-1]}: {info}")
            time.sleep(0.5)

print("\nturbidity estimate (Nechad 2009, 665 nm: T = A*rho/(1-rho/C), A=228.1, C=0.1641) for each clear item at the pier")
for it in clear[:6]:
    out = []
    for name, lon, lat in points:
        res = {}
        for asset in ("B04", "SCL"):
            rr = c.get(f"{PC}/data/v1/item/bbox/{lon-d},{lat-d},{lon+d},{lat+d}/30x30.npy",
                       params={"collection": "sentinel-2-l2a", "item": it["id"], "assets": asset})
            if rr.status_code == 200 and rr.content[:6] == b"\x93NUMPY":
                res[asset] = np.load(io.BytesIO(rr.content))
            time.sleep(0.3)
        if "B04" in res and "SCL" in res:
            b4 = res["B04"][0].astype(float)
            scl = res["SCL"][0]
            water = scl == 6
            # L2A reflectance = (DN - 1000) / 10000 after processing baseline 04.00
            rho = (b4[water] - 1000) / 10000 if water.any() else np.array([])
            if rho.size:
                med = float(np.median(rho))
                t = 228.1 * med / (1 - med / 0.1641) if med < 0.16 else float("nan")
                out.append(f"{name}: {water.sum()} water px, rho665 {med:.4f}, ~{t:.2f} FNU")
            else:
                out.append(f"{name}: no water pixels (SCL classes {np.unique(scl).tolist()})")
    print(f"  {it['properties']['datetime'][:16]} cloud {it['properties'].get('eo:cloud_cover'):.0f}: " + "; ".join(out))
PY
