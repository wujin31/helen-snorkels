# Data sources

What the pipeline reads, how often it's archived (`config/sources.yaml`), and
how each ID was found. Everything here was confirmed against the live
services on 2026-09-27 with `probe.yml` (branches `probe/discovery-*`).

| Source id | What | Archive cadence | Used by v0 scorer |
|---|---|---|---|
| `cam.scripps_pier` | One still from the Scripps Pier underwater cam via the HDOnTap embed endpoint that the Shore Stations' PierViz page uses (`scripps_pier-underwater-CUST`), decoded with ffmpeg; falls back to the public page's HLS URL, then a headless browser | 15 min, sun ≥ 2° | Not yet (Phase 3 CV) |
| `tides.predictions` | NOAA CO-OPS 9410230, 6-min + highs/lows, MLLW | 6 h | Tide curve, trend, best window |
| `tides.observed` | CO-OPS water level, water temp, wind, air temp | 1 h | Pier wind (primary), water temp (fallback) |
| `weather.ndbc_ljpc1` | NDBC LJPC1 (same pier station), trimmed to 6 h | 1 h | Pier wind (fallback) |
| `weather.openmeteo_forecast` | Hourly wind, gusts, precipitation for both spots | 1 h | Window wind, rain gate |
| `weather.openmeteo_marine` | Hourly waves/swell/SST for both spots | 1 h | Waves (last-resort fallback) |
| `weather.nws_grid` | NWS SGX gridpoint forecast (land point) | 3 h | Archive only |
| `weather.nws_alerts` | NWS active alerts at a land and a nearshore point | 1 h | High Surf → No; Beach Hazards / Rip Current → caps at Maybe |
| `cdip.buoy` | Buoy 201 Scripps Nearshore, last 3 h incl. full spectra + SST | 30 min | Waves (fallback) |
| `cdip.mop_nowcast` | MOP alongshore nowcast incl. spectra: **D0482** (Cove, 0.18 km, 10 m, normal 18°), **D0496** (Marine Room, 0.34 km, 10 m, normal 318°) | 1 h | Waves (primary), orbital velocity, decay |
| `cdip.mop_forecast` | MOP forecast files, as issued | 12 h | Archive only (Phase 7) |
| `sccoos.pier` | CeNCOOS ERDDAP `scripps-pier-automated-shore-sta-1`: temperature, chlorophyll (ECO), **turbidity (ECO, NTU)**, O₂, salinity | 30 min | Water temp, chlorophyll, turbidity → visibility |
| `sccoos.habs` | SCCOOS ERDDAP `HABs-ScrippsPier` weekly samples (chlorophyll, domoic acid, cell counts) | daily | Archive only (bloom notes later) |
| `water_quality.county` | County DEHQ sdbeachinfo.com site list with advisory levels (OutSystems screen service `ScreenDataSetGetSiteById`) | 1 h | Advisory/closure → No |
| `coastwatch.viirs` | CoastWatch `noaacwNPPVIIRSkd490SectorVYDaily` (750 m), `kd_490` box around each spot | daily | Archive only (Tier 3 clarity) |

## How IDs were found

- **MOP points:** `snorkel discover-mops` bisects the THREDDS catalog
  (`cdip/model/MOP_alongshore`, 1,210 San Diego points D0001–D1210) on
  latitude, then ranks neighbours by distance. The shore normals agree with
  the spots: the Cove faces north, the Marine Room reach faces WNW–NW.
- **County sites:** 90 sampling sites come back from the screen service.
  La Jolla Cove is **105**; the Marine Room is between **106** (Ave De La
  Playa, 32.8548, -117.2598) and **54** (Vallecitos). `PriorityMax` is each
  site's worst active event: 1 open, 2 advisory, 4 closure (and 3 the page's
  "warning"), confirmed against the page's own counts (8 advisories, 4
  closures) on 2026-09-27.
- **County API version:** read from the app's
  `CoSD_Beach_Water_CW.MainFlow.HomeBlockNew.mvc.js` whenever the server
  reports it changed, so a county redeploy doesn't break the fetcher.
- **CoastWatch sector:** the "VY" sector spans 0–45°N, 120–60°W. The West
  Coast node's ERDDAP blocks GitHub runner IPs, so the central node is used.

## Known access limits

- **CDIP** sometimes answers GitHub-runner requests with "Access Denied. Please
  contact us at www@cdip.ucsd.edu" (it varies by runner IP). The scorer then
  falls back to the archiver's latest CDIP snapshot (`pipeline.latest_archived`),
  so a refused runner doesn't change the call. The buoy is archived hourly to
  keep load low. A note to CDIP is drafted in `docs/cdip-note.md`.
- **CoastWatch West Coast ERDDAP** blocks GitHub runner IPs; the central node is used.
- Offshore waves (buoy, Open-Meteo) are scaled by the spot's exposure to their
  direction before gating, and the coarse model alone only rules a day out when
  it's 1.5x over the limit (`rules.COARSE_MODEL_GATE_FACTOR`).

## Not used

- **Swim Guide:** its JSON API requires authentication; the county is the
  primary source anyway.
- **HDOnTap thumbnails:** a static `snapshot_…jpg` exists, but its refresh
  rate is unknown; the embed stream gives a guaranteed-current frame.

## Probing

`uv run snorkel probe <source> [--save-fixture]` hits one source now.
`snorkel sniff <url>` lists the requests a page makes (how the county and
cam endpoints were found). To run either from a GitHub runner, push a branch
named `probe/<anything>` containing `probe/run.sh` (see
`.github/workflows/probe.yml`).
