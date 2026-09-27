#!/usr/bin/env bash
# Discovery round 2.
set -u
section() { printf '\n\n======== %s ========\n' "$*"; }
UA="snorkel-status/0.1 (+https://github.com/wujin31/helen-snorkels)"

section "Swim Guide: beach 1986"
curl -sA "$UA" https://www.theswimguide.org/server/beaches/1986 | head -c 3000; echo
section "Swim Guide: advisories 1986"
curl -sA "$UA" https://www.theswimguide.org/server/beaches/1986/advisories | head -c 3000; echo
section "Swim Guide: nearby Marine Room"
curl -sA "$UA" "https://www.theswimguide.org/server/beaches/nearby?sort=nearby&limit=8&offset=0&lat=32.8532&lng=-117.2598" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('beaches') or d.get('data') or d
print(json.dumps(items, indent=1)[:5000])"
section "Swim Guide: quality history 1986"
curl -sA "$UA" "https://www.theswimguide.org/server/beaches/1986/quality/history?groupBy=year" | head -c 1500; echo

section "HDOnTap embed backend (as used by coollab.ucsd.edu/pierviz)"
curl -sA "$UA" -H "Referer: https://coollab.ucsd.edu/" "https://portal.hdontap.com/backend/embed/scripps_pier-underwater-CUST?r=aHR0cHM6Ly9jb29sbGFiLnVjc2QuZWR1" | head -c 3000; echo
section "HDOnTap thumbnail freshness"
for i in 1 2; do
  curl -sI "https://storage.hdontap.com/wowza_stream_thumbnails/snapshot_hosb6_scripps_pier-underwater.stream_rPDJOFt.jpg" | grep -iE "last-modified|content-length|date|cache-control|age"
  sleep 90
done
section "cam probe (static page, should be hls now)"
uv run snorkel probe cam.scripps_pier

section "CoastWatch sectors covering 32.85N -117.27E"
for s in UW UX UY UZ VW VX VY VZ WU WX WY WZ XW XX XY XZ YW YX YY YZ ZW ZX ZY ZZ; do
  id="noaacwNPPVIIRSkd490Sector${s}Daily"
  info=$(curl -s "https://coastwatch.noaa.gov/erddap/info/$id/index.csv" | grep -E "geospatial_lat_(min|max)|geospatial_lon_(min|max)|,title," | awk -F, '{print $3"="$5}' | tr '\n' ' ')
  echo "$id $info"
  sleep 1
done
section "CoastWatch global daily kd490 variables"
curl -s "https://coastwatch.noaa.gov/erddap/info/noaacwNPPVIIRSkd490Daily/index.csv" | grep -E "^(variable|dimension)," | head
curl -s "https://coastwatch.noaa.gov/erddap/info/noaacwNPPVIIRSchlaDaily/index.csv" | grep -E "^(variable|dimension)," | head
curl -s "https://coastwatch.noaa.gov/erddap/search/index.csv?searchFor=VIIRS%20chlorophyll%20daily%20sector" | cut -d, -f16 | grep -i sector | head -5

section "HABs Scripps Pier"
curl -s "https://erddap.sccoos.org/erddap/tabledap/HABs-ScrippsPier.csv?&time%3E=now-60days" | head -5 | cut -c1-1500

section "sdbeachinfo screenservices (request bodies + responses)"
uv run python - <<'PY'
from playwright.sync_api import sync_playwright
KEYS = ("GetClosures", "GetWarnings", "GetAdvisoriesCount", "GetRegionsCentral", "GetDataForHomeCache", "GetLastDateTime", "GetSiteById", "moduleversioninfo")
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    def on_response(resp):
        if any(k in resp.url for k in KEYS):
            req = resp.request
            print("\n---", req.method, resp.status, resp.url)
            print("req headers:", {k: v for k, v in req.headers.items() if k.lower().startswith(("x-", "content-type", "outsystems"))})
            print("req body:", (req.post_data or "")[:1500])
            try:
                print("resp:", resp.text()[:4000])
            except Exception as e:
                print("resp error", e)
    page.on("response", on_response)
    page.goto("https://www.sdbeachinfo.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(25000)
    b.close()
PY

section "MOP nowcast + forecast + buoy fixtures"
uv run snorkel probe cdip.mop_nowcast --save-fixture | grep -E "^(OK|ERROR|  saved)"
uv run snorkel probe cdip.buoy --save-fixture | grep -E "^(OK|ERROR|  saved)"
curl -sI "https://thredds.cdip.ucsd.edu/thredds/fileServer/cdip/model/MOP_alongshore/D0482_forecast.nc" | grep -i content-length
uv run python - <<'PY'
import xarray as xr, glob
for f in sorted(glob.glob("tests/fixtures/cdip.*/*.nc")):
    ds = xr.open_dataset(f)
    print(f, dict(ds.sizes))
    for name in ("waveHs", "waveTp", "waveDp", "waveTime", "metaShoreNormal"):
        if name in ds.variables:
            print("  ", name, ds[name].values[-3:] if ds[name].ndim else ds[name].values)
PY
du -ah tests/fixtures | sort -h | tail -12
