# Data sources

What the pipeline reads, how often it's archived (`config/sources.yaml`), and
how each ID was found. Everything here was confirmed against the live
services on 2026-09-27 with `probe.yml` (branches `probe/discovery-*`).

| Source id | What | Archive cadence | Used by v0 scorer |
|---|---|---|---|
| `tides.predictions` | NOAA CO-OPS 9410230, 6-min + highs/lows, MLLW | 6 h | Tide curve, trend, best window |
| `tides.observed` | CO-OPS water level, water temp, wind, air temp | 1 h | Pier wind (primary), water temp (fallback) |
| `weather.ndbc_ljpc1` | NDBC LJPC1 (same pier station), trimmed to 6 h | 1 h | Pier wind (fallback) |
| `weather.openmeteo_forecast` | Hourly wind, gusts, precipitation at every spot | 1 h | Window wind, rain gate |
| `weather.openmeteo_marine` | Hourly waves/swell/SST at every spot | 1 h | Waves (last-resort fallback) |
| `weather.nws_srf` | NWS Surf Zone Forecast (SGX), San Diego County Coastal Areas segment: surf height, rip current risk, water temp, swell remarks for today and the next day | 3 h | High rip risk caps a spot at Maybe; surf and rip risk shown in Why and Water today |
| `weather.nws_grid` | NWS SGX gridpoint forecast (land point) | 3 h | Archive only |
| `weather.nws_alerts` | NWS active alerts at a land and a nearshore point | 1 h | High Surf → No; Beach Hazards / Rip Current → caps at Maybe |
| `cdip.buoy` | Buoy 201 Scripps Nearshore, last 3 h incl. full spectra + SST | 30 min | Waves (fallback) |
| `cdip.mop_nowcast` | MOP alongshore nowcast incl. spectra, one point per spot (`cdip_mop_id` in `config/spots.yaml`; e.g. **D0482** Cove, 0.18 km, 10 m, normal 18°; **D0496** Marine Room, 0.34 km, 10 m, normal 318°) | 1 h | Waves (primary), orbital velocity, decay |
| `cdip.mop_forecast` | MOP forecast files, as issued | 12 h | Archive only (Phase 7) |
| `sccoos.pier` | CeNCOOS ERDDAP `scripps-pier-automated-shore-sta-1`: temperature, chlorophyll (ECO), **turbidity (ECO, NTU)**, O₂, salinity | 30 min | Water temp, chlorophyll, turbidity → visibility |
| `sccoos.habs` | SCCOOS ERDDAP `HABs-ScrippsPier` weekly samples (chlorophyll, domoic acid, cell counts) | daily | Archive only (bloom notes later) |
| `water_quality.county` | County DEHQ sdbeachinfo.com site list with advisory levels (OutSystems screen service `ScreenDataSetGetSiteById`) | 1 h | Advisory/closure → No |
| `coastwatch.viirs` | CoastWatch `noaacwNPPVIIRSkd490SectorVYDaily` (750 m), `kd_490` box around each spot | daily | Archive only: tested against the pier sensor and doesn't track it (see Not used) |

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

## Visibility model (calibrated 2026-10-06)

No public sensor measures visibility, and the dive-report archives that could
(Just Get Wet / DiveViz) block automated reads until they say yes
(`docs/dive-report-request.md`). The one measured clarity signal is the
Scripps Pier ECO turbidity sensor, so the estimate is fitted to it: a
backtest on `probe/calibrate` lined up 915 hourly daylight readings from
Jul 4 to Oct 5 with the decayed near-bottom orbital velocity at MOP D0496
(spectral, 4 m), pier chlorophyll, pier wind and Open-Meteo rain.

| Against pier turbidity (Spearman) | hourly | daily |
|---|---|---|
| Near-bottom wave motion, 24 h half-life (12-48 h equal) | +0.51 | +0.58 |
| Wave height at the spot | +0.50 | +0.53 |
| Chlorophyll | +0.41 | +0.42 |
| Wind | +0.04 | +0.08 |
| Rain, last 5 days (only 3 rainy days) | -0.10 | -0.12 |

The fitted model, `ln NTU = -1.80 + 3.5 * orbital + 0.49 * ln(chl)`, feeds the
same turbidity-to-feet curve as the sensor (`config/scoring.yaml`). Fit on one
half of the summer and tested on the other, it tracks the sensor at Spearman
0.56-0.70 with a typical error of ~5 ft, and its +/-35% band holds the
sensor's reading 72-76% of the time. The hand-set proxy it replaces read
~10 ft low (band hit rate 19%). Caveats: the feet still rest on the
turbidity-to-feet prior (9 ft at 1 NTU), the fit is at one sandy spot near
the pier, and summer had no rain or bloom to test those terms. Dive reports
are what would settle all three.

Two guardrails keep it inside what was fitted: wave motion calmer than the
data (`min_orbital_ms`, 0.15 m/s) or with less plankton than its clearest
days (`min_chl_ug_l`, 0.3 ug/L) isn't read as any clearer, and Mission
Point, where the ebb carries Mission Bay water the wave model can't see, is
capped at 15 ft (`max_vis_ft` in `config/spots.yaml`, a prior). Without the
cap, the first live run put Mission Point at 26-40 ft and made it the best
bet.

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

- **Satellite water color, per spot** (tested 2026-10-06 on `probe/embed-check`).
  The idea was turbidity right off each beach from satellite reflectance, where
  no sensor exists. Both products were checked against the Scripps Pier ECO
  turbidity and chlorophyll sensors, the only measured clarity nearby:
  - *Sentinel-2 L2A* (20 m, every 2-5 days, via Microsoft Planetary Computer):
    red-band (B04) water reflectance, NIR-masked, minus an offshore reference
    in the same scene, on 9 clear passes since July. No relationship: on the
    murkiest day (1.75 NTU) the pier pixel read clearer than offshore, on a
    0.17 NTU day too, and several readings were negative (Sen2Cor
    over-corrects dark water). At 1 NTU the expected signal is ~0.004 in
    reflectance, about the product's noise over water. La Jolla's usual range
    (0.2-2 NTU) is below what it can resolve; only big runoff or bloom
    plumes would show, and those already arrive through the rain rules and
    the pier's chlorophyll.
  - *VIIRS Kd490 and chlorophyll* (750 m, daily, CoastWatch): over 41
    cloud-free days near the pier, Spearman -0.13 (wide box) and 0.01 (near
    box) against pier turbidity, ~0.3 against pier chlorophyll. North County
    and Point Loma boxes were no better. Too coarse for water within a few
    hundred metres of shore. Still archived (`coastwatch.viirs`), since the
    near-real-time product only keeps ~90 days.

- **SCCOOS HABs plankton counts** (`sccoos.habs`, still archived): the weekly
  red-tide cell counts post about six weeks after sampling (2026-10-06: newest
  counts were from Aug 17), too late for a daily call. A red tide shows up in
  real time as high chlorophyll on the pier sensor, which the visibility
  estimate already uses.

- **Swim Guide:** its JSON API requires authentication; the county is the
  primary source anyway.
- **The Scripps Pier underwater cam** (retired 2026-10-06). HDOnTap's players
  refuse to be framed by other sites (`X-Frame-Options: DENY`; the portal
  players' CSP `frame-ancestors` allows only `*.hdontap.com`, or only UCSD sites
  for Scripps' copy), and permission to embed or analyze the stream wasn't
  granted. Capture stopped and every archived frame was deleted
  (`snorkel purge-cam`, via `maintenance.yml`). The page links to Scripps'
  PierViz page instead.

## Probing

`uv run snorkel probe <source> [--save-fixture]` hits one source now.
`snorkel sniff <url>` lists the requests a page makes (how the county
endpoint was found). To run either from a GitHub runner, push a branch
named `probe/<anything>` containing `probe/run.sh` (see
`.github/workflows/probe.yml`).
