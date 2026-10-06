"""Everything the scorer knows at one moment, gathered from all sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from snorkel.observations import (
    Alert,
    Chlorophyll,
    PrecipObs,
    SourceResult,
    SurfForecast,
    Tides,
    Turbidity,
    WaterQuality,
    WaterTemp,
    WaveSeries,
    WindSeries,
)


@dataclass
class Conditions:
    now: datetime
    tides: SourceResult[Tides] | None = None
    waves: dict[str, SourceResult[WaveSeries]] = field(default_factory=dict)
    """Best available wave series per spot id (MOP, else buoy, else Open-Meteo)."""
    wind_obs: SourceResult[WindSeries] | None = None
    """Measured wind at Scripps Pier."""
    wind_forecast: dict[str, SourceResult[WindSeries]] = field(default_factory=dict)
    """Hourly forecast wind per spot id."""
    precip: dict[str, SourceResult[list[PrecipObs]]] = field(default_factory=dict)
    """Hourly precipitation per spot id, past days and forecast."""
    water_temp: SourceResult[WaterTemp] | None = None
    chlorophyll: SourceResult[Chlorophyll] | None = None
    turbidity: SourceResult[Turbidity] | None = None
    water_quality: dict[str, SourceResult[WaterQuality]] = field(default_factory=dict)
    alerts: SourceResult[list[Alert]] | None = None
    surf_forecast: SourceResult[SurfForecast] | None = None
    """NWS Surf Zone Forecast for San Diego County beaches."""

    def all_results(self) -> list[SourceResult]:  # type: ignore[type-arg]
        singles = [
            self.tides,
            self.wind_obs,
            self.water_temp,
            self.chlorophyll,
            self.turbidity,
            self.alerts,
            self.surf_forecast,
        ]
        groups = [self.waves, self.wind_forecast, self.precip, self.water_quality]
        out = [r for r in singles if r is not None]
        for group in groups:
            out.extend(group.values())
        return out
