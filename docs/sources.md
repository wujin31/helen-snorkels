# Data sources

What the archiver captures (`config/sources.yaml`), how often, and what's still
unconfirmed. "Confirmed" means probed against the live service.

| Source id | Provider / endpoint | Cadence | Status |
|---|---|---|---|
| `cam.scripps_pier` | HDOnTap stream page → snapshot / HLS / headless browser | 15 min, sun ≥ 2° | **Unconfirmed**: capture method not probed yet; permission request drafted (`docs/scripps-cam-request.md`) |
| `tides.predictions` | NOAA CO-OPS datagetter, 9410230, 6-min + hi/lo, MLLW | 6 h | Unconfirmed (well-documented API) |
| `tides.observed` | CO-OPS water level, water temp, wind, air temp (last 6 h) | 1 h | Unconfirmed |
| `weather.ndbc_ljpc1` | NDBC realtime2 `LJPC1.txt`, trimmed to 6 h | 1 h | Unconfirmed |
| `weather.openmeteo_forecast` | Open-Meteo forecast, hourly wind/precip, all spots in one call | 1 h | Unconfirmed |
| `weather.openmeteo_marine` | Open-Meteo marine, hourly waves/swell/SST | 1 h | Unconfirmed |
| `weather.nws_grid` | api.weather.gov points → forecastGridData (land point) | 3 h | Unconfirmed |
| `weather.nws_alerts` | api.weather.gov active alerts at land + nearshore points | 1 h | Unconfirmed |
| `cdip.buoy` | THREDDS OPeNDAP `cdip/realtime/201p1_rt.nc`, last 3 h incl. spectra | 30 min | Unconfirmed; buoy 201 = Scripps Nearshore |
| `cdip.mop_nowcast` | THREDDS OPeNDAP `cdip/model/MOP_alongshore/<MOP>_nowcast.nc` | 1 h | **Blocked on MOP IDs** |
| `cdip.mop_forecast` | THREDDS fileServer `<MOP>_forecast.nc` | 12 h | **Blocked on MOP IDs** |
| `sccoos.pier` | CeNCOOS ERDDAP `scripps-pier-automated-shore-sta-1`, last 2 h | 30 min | Unconfirmed |
| `sccoos.habs` | habs.sccoos.org/scripps-pier page | daily | Unconfirmed; look for an ERDDAP dataset instead |
| `water_quality.sdbeachinfo` | sdbeachinfo.com (home page placeholder) | 1 h | **Needs endpoint discovery** |
| `water_quality.swimguide` | theswimguide.org/beach/1986 (La Jolla Cove) | 6 h | Unconfirmed; find the Shores page too |
| `coastwatch.viirs` | CoastWatch ERDDAP griddap, VIIRS Kd490 + chl | daily | **Needs dataset IDs** |

## To look up (needs network access to these hosts)

- **MOP IDs** for the Cove and the Marine Room: the nearest MOP alongshore point
  to each spot, checked against its shore normal. San Diego County MOPs are
  numbered south→north as `D0xxx`. Fill `cdip_mop_id` in `config/spots.yaml`.
- **Water quality**: the station IDs for La Jolla Cove and La Jolla Shores on
  sdbeachinfo.com, and whichever JSON/HTML endpoint the site's map uses. Fill
  `water_quality_ids` and replace the placeholder URL.
- **CoastWatch**: the VIIRS Kd490 and chlorophyll daily 750 m sector dataset
  covering Southern California, its variable names, and whether it has an
  altitude axis or descending latitude.
- **Cam**: whether HDOnTap exposes a still/thumbnail URL; otherwise how the
  embed loads its HLS stream (static HTML vs. JS/API, token lifetime,
  Referer requirement).
- **HABs**: an ERDDAP dataset for the weekly Scripps Pier HAB samples.

Use `uv run snorkel probe <source> --save-fixture` to hit one source and save
what comes back as a test fixture.
