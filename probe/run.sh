#!/usr/bin/env bash
# Discovery round 1: IDs, hidden endpoints, and fixtures for the parsers.
set -u
section() { printf '\n\n======== %s ========\n' "$*"; }

section "MOP discovery"
timeout 900 uv run snorkel discover-mops --window 20

section "CDIP buoy subset: what's in it"
uv run snorkel probe cdip.buoy --save-fixture | head -5
uv run python - <<'PY'
import xarray as xr, glob
for f in glob.glob("tests/fixtures/cdip.buoy/*.nc"):
    ds = xr.open_dataset(f)
    print(f, dict(ds.sizes))
    for name, var in sorted(ds.variables.items(), key=lambda kv: -kv[1].nbytes)[:25]:
        print(f"  {name:32} {var.dims} {var.dtype} {var.nbytes}")
PY

section "sdbeachinfo: requests"
timeout 120 uv run snorkel sniff https://www.sdbeachinfo.com/ --wait 25
section "sdbeachinfo: raw html"
curl -sL https://www.sdbeachinfo.com/ | head -c 3000

section "Swim Guide: requests"
timeout 120 uv run snorkel sniff https://www.theswimguide.org/beach/1986 --wait 20 | grep -iv "google\|analytics\|facebook\|doubleclick\|hotjar" | head -80

section "HDOnTap cam: requests"
timeout 120 uv run snorkel sniff https://hdontap.com/stream/018408/scripps-pier-underwater-live-webcam/ --wait 25 | grep -iv "google\|analytics\|facebook\|doubleclick\|ads" | head -120
section "HDOnTap cam: m3u8/snapshot/embed mentions in static html"
curl -sL https://hdontap.com/stream/018408/scripps-pier-underwater-live-webcam/ | grep -oiE "https?://[^\"' <>]*(m3u8|snapshot|thumbnail|embed|portal)[^\"' <>]*" | sort -u | head -40
section "coollab pierviz: requests"
timeout 120 uv run snorkel sniff https://coollab.ucsd.edu/pierviz/ --wait 20 | head -80

section "cam probe"
uv run snorkel probe cam.scripps_pier

section "CoastWatch ERDDAP search (central)"
curl -sL "https://coastwatch.noaa.gov/erddap/search/index.csv?page=1&itemsPerPage=50&searchFor=VIIRS%20kd490" | cut -c1-300 | head -40
section "CoastWatch ERDDAP search (West Coast node)"
curl -sL "https://coastwatch.pfeg.noaa.gov/erddap/search/index.csv?page=1&itemsPerPage=50&searchFor=VIIRS%20kd490" | cut -c1-300 | head -40

section "SCCOOS ERDDAP HAB search"
curl -sL "https://erddap.sccoos.org/erddap/search/index.csv?page=1&itemsPerPage=50&searchFor=HABs%20scripps" | cut -c1-300 | head -20

section "Fixtures for parsers"
for s in tides.predictions tides.observed weather.ndbc_ljpc1 weather.openmeteo_forecast weather.openmeteo_marine weather.nws_alerts sccoos.pier; do
  uv run snorkel probe "$s" --save-fixture | grep -E "^(OK|ERROR|  saved)"
done
section "SCCOOS pier CSV head"
head -4 tests/fixtures/sccoos.pier/*.csv | cut -c1-600
section "Fixture sizes"
du -ah tests/fixtures | sort -h | tail -30
