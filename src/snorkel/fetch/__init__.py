"""Source registry: source id (as in config/sources.yaml) -> capture function."""

from __future__ import annotations

from snorkel.fetch import cam, cdip, coastwatch, sccoos, tides, water_quality, weather
from snorkel.fetch.base import SourceFn

SOURCES: dict[str, SourceFn] = {
    "cam.scripps_pier": cam.capture,
    "tides.predictions": tides.capture_predictions,
    "tides.observed": tides.capture_observed,
    "weather.ndbc_ljpc1": weather.capture_ndbc,
    "weather.openmeteo_forecast": weather.capture_openmeteo_forecast,
    "weather.openmeteo_marine": weather.capture_openmeteo_marine,
    "weather.nws_grid": weather.capture_nws_grid,
    "weather.nws_alerts": weather.capture_nws_alerts,
    "cdip.buoy": cdip.capture_buoy,
    "cdip.mop_nowcast": cdip.capture_mop_nowcast,
    "cdip.mop_forecast": cdip.capture_mop_forecast,
    "sccoos.pier": sccoos.capture_pier,
    "sccoos.habs": sccoos.capture_habs,
    "water_quality.sdbeachinfo": water_quality.capture_pages,
    "water_quality.swimguide": water_quality.capture_pages,
    "coastwatch.viirs": coastwatch.capture_viirs,
}
