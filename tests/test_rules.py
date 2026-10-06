from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from snorkel.config import load_spots
from snorkel.models import SpotConfig
from snorkel.observations import (
    Alert,
    Chlorophyll,
    PrecipObs,
    SourceResult,
    TidePoint,
    Tides,
    Turbidity,
    WaterQuality,
    WaveObs,
    WaveSeries,
    WindObs,
    WindSeries,
)
from snorkel.score.conditions import Conditions
from snorkel.score.config import ScoringConfig, load_scoring
from snorkel.score.rules import compass, score_spot
from snorkel.sun import LOCAL_TZ, sun_times

NOW = datetime(2026, 9, 27, 13, 30, tzinfo=UTC)  # 6:30 am PDT
LAT, LON = 32.8666, -117.2571


@pytest.fixture
def cfg() -> ScoringConfig:
    return load_scoring()


@pytest.fixture
def cove() -> SpotConfig:
    return next(s for s in load_spots() if s.id == "la-jolla-cove")


def ok(source: str, value: object, now: datetime = NOW) -> SourceResult:  # type: ignore[type-arg]
    return SourceResult(source=source, ok=True, fetched_at=now, valid_at=now, value=value)


def tides(start: datetime, hours: int = 72, phase_h: float = 0.0) -> Tides:
    points = []
    for i in range(hours * 10 + 1):
        t = start + timedelta(minutes=6 * i)
        h = 0.8 + 0.7 * math.sin(2 * math.pi * ((i * 0.1) - phase_h) / 12.42)
        points.append(TidePoint(time=t, height_m=h))
    return Tides(station="9410230", points=points)


def hourly(start: datetime, hours: int) -> list[datetime]:
    return [start + timedelta(hours=i) for i in range(hours)]


def waves(hs_m: float, tp_s: float = 12, dp: float = 285, source: str = "mop") -> WaveSeries:
    obs = [
        WaveObs(time=t, hs_m=hs_m, tp_s=tp_s, dp_deg=dp)
        for t in hourly(NOW - timedelta(hours=72), 73)
    ]
    return WaveSeries(source=source, site="D0000", obs=obs)  # type: ignore[arg-type]


def wind(speed_ms: float, now: datetime = NOW) -> WindSeries:
    obs = [
        WindObs(time=t, speed_ms=speed_ms, dir_deg=280)
        for t in hourly(now - timedelta(hours=6), 60)
    ]
    return WindSeries(source="openmeteo", obs=obs)


def dry(now: datetime = NOW) -> list[PrecipObs]:
    return [PrecipObs(time=t, mm=0.0) for t in hourly(now - timedelta(hours=160), 161)]


def conditions(spot: SpotConfig, now: datetime = NOW, **overrides: object) -> Conditions:
    cond = Conditions(
        now=now,
        tides=ok("tides", tides(now - timedelta(hours=12)), now),
        waves={spot.id: ok("waves", waves(0.3, 10), now)},
        wind_forecast={spot.id: ok("wind", wind(1.5, now), now)},
        precip={spot.id: ok("precip", dry(now), now)},
        chlorophyll=ok("chl", Chlorophyll(time=now, chl_ug_l=1.0), now),
        water_quality={
            spot.id: ok("wq", WaterQuality(status="open", station="EH-010"), now),
        },
        alerts=ok("alerts", [], now),
    )
    for key, value in overrides.items():
        setattr(cond, key, value)
    return cond


def score(spot: SpotConfig, cond: Conditions, cfg: ScoringConfig):  # noqa: ANN201
    day = cond.now.astimezone(LOCAL_TZ).date()
    return score_spot(
        spot,
        cond,
        cfg,
        sun_times(LAT, LON, day),
        sun_times(LAT, LON, day + timedelta(days=1)),
    )


def test_calm_clean_morning_is_a_yes(cove: SpotConfig, cfg: ScoringConfig) -> None:
    status = score(cove, conditions(cove), cfg)
    assert status.verdict == "yes", status.reason
    assert status.vis_ft and status.vis_ft[0] >= 10
    assert status.window is not None and status.window_day == "today"
    assert "vis" in status.reason
    assert not status.gates
    assert "safe" not in status.reason.lower()


def test_water_quality_advisory_is_a_no(cove: SpotConfig, cfg: ScoringConfig) -> None:
    wq = {cove.id: ok("wq", WaterQuality(status="advisory", station="105", detail="La Jolla Cove"))}
    status = score(cove, conditions(cove, water_quality=wq), cfg)
    assert status.verdict == "no"
    assert status.confidence == "high"
    assert status.reason == "County water-quality advisory at La Jolla Cove"
    assert status.window is None


def test_unknown_water_quality_caps_at_maybe(cove: SpotConfig, cfg: ScoringConfig) -> None:
    status = score(cove, conditions(cove, water_quality={}), cfg)
    assert status.verdict == "maybe"
    assert "Water-quality status unknown" in status.reason


def test_big_swell_is_a_no(cove: SpotConfig, cfg: ScoringConfig) -> None:
    big = {cove.id: ok("waves", waves(1.3, 14))}
    status = score(cove, conditions(cove, waves=big), cfg)
    assert status.verdict == "no"
    assert status.reason.startswith("Waves ~4 ft")


def test_rain_within_72h_is_a_no(cove: SpotConfig, cfg: ScoringConfig) -> None:
    rain = dry()
    rain[-40] = PrecipObs(time=rain[-40].time, mm=6.0)
    status = score(cove, conditions(cove, precip={cove.id: ok("precip", rain)}), cfg)
    assert status.verdict == "no"
    assert "county 72 h advisory" in status.reason


def test_older_rain_only_costs_visibility(cove: SpotConfig, cfg: ScoringConfig) -> None:
    rain = dry()
    rain[-100] = PrecipObs(time=rain[-100].time, mm=6.0)
    clean = score(cove, conditions(cove), cfg)
    after = score(cove, conditions(cove, precip={cove.id: ok("precip", rain)}), cfg)
    assert after.verdict != "no"
    assert clean.vis_ft and after.vis_ft and after.vis_ft[1] < clean.vis_ft[1]


def test_no_wave_data_is_unknown(cove: SpotConfig, cfg: ScoringConfig) -> None:
    status = score(cove, conditions(cove, waves={}), cfg)
    assert status.verdict == "unknown"
    assert status.vis_ft is None


def test_stale_waves_are_ignored(cove: SpotConfig, cfg: ScoringConfig) -> None:
    old = SourceResult(
        source="waves",
        ok=True,
        fetched_at=NOW - timedelta(hours=10),
        valid_at=NOW - timedelta(hours=10),
        value=waves(0.3),
    )
    status = score(cove, conditions(cove, waves={cove.id: old}), cfg)
    assert status.verdict == "unknown"


def test_coarse_model_waves_cap_at_maybe(cove: SpotConfig, cfg: ScoringConfig) -> None:
    coarse = {cove.id: ok("waves", waves(0.3, 10, source="openmeteo"))}
    status = score(cove, conditions(cove, waves=coarse), cfg)
    assert status.verdict == "maybe"
    assert "coarse" in status.reason


def test_high_surf_advisory_is_a_no(cove: SpotConfig, cfg: ScoringConfig) -> None:
    alerts = ok("alerts", [Alert(event="High Surf Advisory")])
    status = score(cove, conditions(cove, alerts=alerts), cfg)
    assert status.verdict == "no"
    assert status.reason == "NWS High Surf Advisory"


def test_wind_all_day_is_a_no(cove: SpotConfig, cfg: ScoringConfig) -> None:
    windy = {cove.id: ok("wind", wind(8.0))}  # ~16 kt
    status = score(cove, conditions(cove, wind_forecast=windy), cfg)
    assert status.verdict == "no"
    assert status.reason.startswith("Wind ~16 kt")


def test_long_period_swell_hurts_vis_more(cove: SpotConfig, cfg: ScoringConfig) -> None:
    short = score(cove, conditions(cove, waves={cove.id: ok("w", waves(0.5, 6))}), cfg)
    long = score(cove, conditions(cove, waves={cove.id: ok("w", waves(0.5, 16))}), cfg)
    assert short.vis_ft and long.vis_ft and long.vis_ft[1] < short.vis_ft[1]


def test_plankton_bloom_hurts_vis(cove: SpotConfig, cfg: ScoringConfig) -> None:
    bloom = ok("chl", Chlorophyll(time=NOW, chl_ug_l=12.0))
    status = score(cove, conditions(cove, chlorophyll=bloom), cfg)
    assert any(f.label == "Plankton" and f.effect == "-" for f in status.factors)
    assert status.vis_ft and status.vis_ft[1] < 20


def test_window_prefers_incoming_tide(cove: SpotConfig, cfg: ScoringConfig) -> None:
    status = score(cove, conditions(cove), cfg)
    assert status.window is not None
    chosen = [s for s in status.hourly if status.window.start <= s.time < status.window.end]
    assert chosen and all(s.tide_trend in ("incoming", "slack") for s in chosen)


def test_evening_plans_tomorrow(cove: SpotConfig, cfg: ScoringConfig) -> None:
    evening = datetime(2026, 9, 28, 2, 30, tzinfo=UTC)  # 7:30 pm PDT
    status = score(cove, conditions(cove, now=evening), cfg)
    assert status.window_day == "tomorrow"
    assert status.window and status.window.start.astimezone(LOCAL_TZ).date() == date(2026, 9, 28)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 11, 1, 13, 0, tzinfo=UTC),  # 6 am PDT, the morning clocks fall back
        datetime(2027, 3, 14, 13, 0, tzinfo=UTC),  # 6 am PDT, the morning clocks spring forward
    ],
)
def test_windows_on_dst_days_stay_in_local_daylight(
    cove: SpotConfig, cfg: ScoringConfig, now: datetime
) -> None:
    status = score(cove, conditions(cove, now=now), cfg)
    assert status.window is not None
    start = status.window.start.astimezone(LOCAL_TZ)
    end = status.window.end.astimezone(LOCAL_TZ)
    sun = sun_times(LAT, LON, start.date())
    assert start >= sun.sunrise and end <= sun.sunset
    assert start.minute in (0, 30) and start.hour >= 6
    assert timedelta(minutes=90) <= end - start <= timedelta(minutes=180)


def test_compass() -> None:
    assert [compass(d) for d in (0, 44, 225, 290, 350)] == ["N", "NE", "SW", "W", "N"]
    assert compass(None) == ""


def test_murky_pier_turbidity_pulls_vis_down_most_near_the_pier(cfg: ScoringConfig) -> None:
    spots = {s.id: s for s in load_spots()}
    murky = ok("turb", Turbidity(time=NOW, ntu=3.0))
    for spot_id in ("marine-room", "la-jolla-cove"):
        spot = spots[spot_id]
        clear = score(spot, conditions(spot), cfg)
        cloudy = score(spot, conditions(spot, turbidity=murky), cfg)
        assert clear.vis_ft and cloudy.vis_ft and cloudy.vis_ft[1] < clear.vis_ft[1]
    near = score(spots["marine-room"], conditions(spots["marine-room"], turbidity=murky), cfg)
    far = score(spots["la-jolla-cove"], conditions(spots["la-jolla-cove"], turbidity=murky), cfg)
    assert near.vis_ft and far.vis_ft and near.vis_ft[1] < far.vis_ft[1]
    assert any(f.label == "Turbidity" and f.effect == "-" for f in near.factors)


def test_offshore_model_waves_are_weighted_by_exposure(cfg: ScoringConfig) -> None:
    room = next(s for s in load_spots() if s.id == "marine-room")
    # 4.3 ft from 320°: the Marine Room is sheltered from that direction -> Maybe, not No.
    sheltered = {room.id: ok("w", waves(1.3, 12, dp=320, source="openmeteo"))}
    status = score(room, conditions(room, waves=sheltered), cfg)
    assert status.verdict == "maybe"
    assert "coarse" in status.reason
    # A big exposed swell still rules it out, even from the coarse model.
    exposed = {room.id: ok("w", waves(1.8, 14, dp=260, source="openmeteo"))}
    status = score(room, conditions(room, waves=exposed), cfg)
    assert status.verdict == "no"
    assert "offshore estimate" in status.reason


def test_buoy_waves_use_exposure_but_no_extra_slack(cove: SpotConfig, cfg: ScoringConfig) -> None:
    exposed = {cove.id: ok("w", waves(0.9, 12, dp=290, source="buoy"))}  # ~3 ft from the NW
    assert score(cove, conditions(cove, waves=exposed), cfg).verdict == "no"
    sheltered = {cove.id: ok("w", waves(0.9, 12, dp=190, source="buoy"))}  # from the S
    assert score(cove, conditions(cove, waves=sheltered), cfg).verdict != "no"


def test_vis_range_never_passes_the_configured_max(cove: SpotConfig, cfg: ScoringConfig) -> None:
    # Flat calm and very clear pier water: the estimate pins to the top.
    clear = ok("turb", Turbidity(time=NOW, ntu=0.2), NOW)
    status = score(
        cove,
        conditions(cove, waves={cove.id: ok("waves", waves(0.05, 8), NOW)}, turbidity=clear),
        cfg,
    )
    assert status.vis_ft is not None
    assert status.vis_ft[1] <= cfg.visibility.max_ft
    assert status.vis_ft[0] >= cfg.visibility.min_ft


def test_impossibly_low_turbidity_is_ignored(cove: SpotConfig, cfg: ScoringConfig) -> None:
    glitch = ok("turb", Turbidity(time=NOW, ntu=0.07), NOW)
    with_glitch = score(cove, conditions(cove, turbidity=glitch), cfg)
    without = score(cove, conditions(cove), cfg)
    assert with_glitch.vis_ft == without.vis_ft
    assert any("too low to trust" in f.detail for f in with_glitch.factors)
