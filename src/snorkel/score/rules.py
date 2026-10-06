"""v0 transparent rules: gates, a visibility proxy, the best window, a verdict.

Every step records why, so the page can say it in one line and expand the
factors on tap. Copy never says "safe"; the best it says is "looks good".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from snorkel.features.tides import height_at, trend_at
from snorkel.features.waves import (
    bottom_orbital_velocity,
    decayed_mean,
    exposure_weight,
    spectral_orbital_velocity,
)
from snorkel.models import SpotConfig
from snorkel.observations import (
    Alert,
    PrecipObs,
    SourceResult,
    WaveObs,
    WaveSeries,
    WindObs,
    WindSeries,
)
from snorkel.score.conditions import Conditions
from snorkel.score.config import ScoringConfig
from snorkel.score.models import (
    Confidence,
    Factor,
    HourScore,
    SpotConditions,
    SpotStatus,
    TimeWindow,
    Verdict,
)
from snorkel.sun import LOCAL_TZ, SunTimes
from snorkel.units import m_to_ft, ms_to_kt

DEFAULT_TP_S = 10.0
COARSE_MODEL_GATE_FACTOR = 1.5  # offshore-model waves must be this far over the limit to gate
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(deg: float | None) -> str:
    if deg is None:
        return ""
    return COMPASS[round((deg % 360) / 45) % 8]


def is_fresh(
    result: SourceResult | None,  # type: ignore[type-arg]
    kind: str,
    cfg: ScoringConfig,
    now: datetime,
) -> bool:
    if result is None or not result.ok or result.value is None:
        return False
    reference = result.valid_at or result.fetched_at
    return now - reference <= timedelta(hours=cfg.staleness_hours.get(kind, 6))


def latest(obs: list[WaveObs] | list[WindObs], now: datetime) -> WaveObs | WindObs | None:
    past = [o for o in obs if o.time <= now]
    return max(past, key=lambda o: o.time) if past else None


def wind_near(series: WindSeries | None, when: datetime) -> WindObs | None:
    if series is None or not series.obs:
        return None
    best = min(series.obs, key=lambda o: abs(o.time - when))
    return best if abs(best.time - when) <= timedelta(minutes=90) else None


def angle_between(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def in_seasonal_closure(spot: SpotConfig, day: date) -> str | None:
    mmdd = day.strftime("%m-%d")
    for closure in spot.seasonal_closures:
        start, end = closure.start, closure.end
        inside = start <= mmdd <= end if start <= end else mmdd >= start or mmdd <= end
        if inside:
            return closure.reason
    return None


def rolling_rain(
    precip: list[PrecipObs], now: datetime, lookback_h: float
) -> list[tuple[datetime, float]]:
    """(hour, mm in the 24 h ending then) for each past hour in the lookback."""
    past = [p for p in precip if now - timedelta(hours=lookback_h + 24) < p.time <= now]
    out = []
    for p in past:
        if p.time <= now - timedelta(hours=lookback_h):
            continue
        window = sum(q.mm for q in past if p.time - timedelta(hours=24) < q.time <= p.time)
        out.append((p.time, window))
    return out


@dataclass
class _Window:
    slots: list[HourScore]
    chosen: TimeWindow | None
    day: Literal["today", "tomorrow"]
    max_wind_kt: float | None


def plan_window(
    spot: SpotConfig,
    cond: Conditions,
    cfg: ScoringConfig,
    sun_today: SunTimes,
    sun_tomorrow: SunTimes,
) -> _Window:
    wc, prefs = cfg.window, cfg.preferences
    step = timedelta(minutes=wc.slot_minutes)
    min_slots = max(1, wc.min_minutes // wc.slot_minutes)
    max_slots = max(min_slots, wc.max_minutes // wc.slot_minutes)
    earliest = time.fromisoformat(prefs.earliest_local)
    tail = timedelta(minutes=prefs.latest_end_before_sunset_min)

    def bounds(sun: SunTimes, floor: datetime | None) -> tuple[datetime, datetime]:
        local_day = sun.sunrise.astimezone(LOCAL_TZ).date()
        start = max(sun.sunrise, datetime.combine(local_day, earliest, LOCAL_TZ).astimezone(UTC))
        if floor is not None:
            start = max(start, floor)
        # Round up to the slot grid so windows read as 7:00, 7:30, ...
        hour = start.replace(minute=0, second=0, microsecond=0)
        start = hour + step * math.ceil((start - hour) / step)
        return start, sun.sunset - tail

    start, end = bounds(sun_today, cond.now)
    day: Literal["today", "tomorrow"] = "today"
    if end - start < step * min_slots:
        start, end = bounds(sun_tomorrow, None)
        day = "tomorrow"

    tides = cond.tides.value if cond.tides and cond.tides.ok and cond.tides.value else None
    forecast = cond.wind_forecast.get(spot.id)
    wind_series = forecast.value if forecast and forecast.ok else None
    mean_tide = (
        sum(p.height_m for p in tides.points) / len(tides.points)
        if tides and tides.points
        else None
    )

    slots: list[HourScore] = []
    t = start
    while t + step <= end:
        mid = t + step / 2
        score = 0.0
        height = height_at(tides.points, mid) if tides else None
        trend = trend_at(tides.points, mid) if tides else None
        prefer = spot.tide_rules.prefer
        if trend and prefer != "any":
            if trend == prefer:
                score += wc.incoming_bonus
            elif trend == "slack":
                if height is not None and mean_tide is not None and height > mean_tide:
                    score += wc.slack_high_bonus
            else:
                score -= wc.outgoing_penalty
        if (
            height is not None
            and spot.min_tide_ft is not None
            and m_to_ft(height) < spot.min_tide_ft
        ):
            score -= wc.below_min_tide_penalty
        wind = wind_near(wind_series, mid)
        wind_kt = ms_to_kt(wind.speed_ms) if wind else None
        if wind_kt is not None:
            score -= wc.wind_weight * (wind_kt / spot.thresholds.max_wind_kt) ** 2
        slots.append(
            HourScore(
                time=t,
                score=round(score, 3),
                tide_ft=round(m_to_ft(height), 2) if height is not None else None,
                tide_trend=trend,
                wind_kt=round(wind_kt, 1) if wind_kt is not None else None,
            )
        )
        t += step

    best: tuple[tuple[float, int], int, int] | None = None
    for i in range(len(slots)):
        for length in range(min_slots, max_slots + 1):
            if i + length > len(slots):
                break
            block = slots[i : i + length]
            key = (round(sum(s.score for s in block) / length, 6), length)
            if best is None or key > best[0]:
                best = (key, i, length)

    chosen = None
    max_wind = None
    if best is not None:
        _, i, length = best
        block = slots[i : i + length]
        chosen = TimeWindow(start=block[0].time, end=block[-1].time + step)
        winds = [s.wind_kt for s in block if s.wind_kt is not None]
        max_wind = max(winds) if winds else None
    return _Window(slots=slots, chosen=chosen, day=day, max_wind_kt=max_wind)


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def sheltered(waves: WaveSeries, factor: float) -> WaveSeries:
    """Scale open-coast waves down for a sheltered spot (height x f, energy x f^2)."""
    return waves.model_copy(
        update={
            "obs": [
                o.model_copy(
                    update={
                        "hs_m": o.hs_m * factor,
                        "energy_m2_hz": [e * factor**2 for e in o.energy_m2_hz]
                        if o.energy_m2_hz
                        else None,
                    }
                )
                for o in waves.obs
            ]
        }
    )


def score_spot(
    spot: SpotConfig,
    cond: Conditions,
    cfg: ScoringConfig,
    sun_today: SunTimes,
    sun_tomorrow: SunTimes,
) -> SpotStatus:
    now = cond.now
    g = cfg.gates
    gates: list[str] = []
    cautions: list[str] = []
    factors: list[Factor] = []
    sc = SpotConditions()

    # Closures and water quality: the first things that make it a No.
    closure = in_seasonal_closure(spot, now.astimezone(LOCAL_TZ).date())
    if closure:
        gates.append(f"Seasonal closure: {closure}")

    wq = cond.water_quality.get(spot.id)
    if is_fresh(wq, "water_quality", cfg, now) and wq and wq.value:
        if wq.value.status in ("advisory", "closure"):
            what = "closure" if wq.value.status == "closure" else "advisory"
            where = f" at {wq.value.detail}" if wq.value.detail else ""
            gates.append(f"County water-quality {what}{where}")
        elif wq.value.status == "open":
            factors.append(Factor(label="Water quality", effect="+", detail="No county advisory"))
        else:
            cautions.append("Water-quality status unknown")
    else:
        cautions.append("Water-quality status unknown")
        factors.append(
            Factor(label="Water quality", effect="~", detail="County status unavailable")
        )

    # NWS hazards.
    alerts: list[Alert] = (
        cond.alerts.value if cond.alerts and cond.alerts.ok and cond.alerts.value else []
    )
    for alert in alerts:
        if alert.event in g.hazard_alerts:
            gates.append(f"NWS {alert.event}")
        elif alert.event in g.caution_alerts:
            cautions.append(f"NWS {alert.event}")
            factors.append(Factor(label=alert.event, effect="-", detail=alert.headline))

    # NWS Surf Zone Forecast: county-wide surf height and rip current risk.
    srf = cond.surf_forecast
    if is_fresh(srf, "surf_forecast", cfg, now) and srf and srf.value:
        period = srf.value.for_day(now.astimezone(LOCAL_TZ).date())
        if period and period.rip_risk == "High" and "NWS Rip Current Statement" not in cautions:
            cautions.append("NWS high rip current risk")
        if period and (period.surf_ft or period.rip_risk):
            parts = []
            if period.surf_ft:
                lo, hi = period.surf_ft
                parts.append(f"surf {lo:g}–{hi:g} ft" if hi > lo else f"surf {hi:g} ft")
            if period.rip_risk:
                parts.append(f"{period.rip_risk.lower()} rip current risk")
            calm = (
                period.surf_ft is not None
                and period.surf_ft[1] <= spot.thresholds.max_hs_ft
                and period.rip_risk == "Low"
            )
            rough = period.rip_risk == "High" or (
                period.surf_ft is not None and period.surf_ft[0] > spot.thresholds.max_hs_ft
            )
            factors.append(
                Factor(
                    label="NWS surf forecast",
                    effect="+" if calm else "-" if rough else "~",
                    detail=", ".join(parts) + " (county beaches)",
                )
            )

    # Rain: the county advises staying out of the water for 72 h after rain.
    rain = cond.precip.get(spot.id)
    recent_rain_penalty = 0.0
    if rain and rain.ok and rain.value is not None:
        lookback = max(g.rain_advisory_hours, cfg.visibility.rain_recent_days * 24)
        sums = rolling_rain(rain.value, now, lookback)
        wet = [t for t, mm in sums if mm >= g.rain_mm_24h]
        if wet:
            last = max(wet)
            hours_ago = (now - last).total_seconds() / 3600
            if hours_ago <= g.rain_advisory_hours:
                gates.append(f"Rain {hours_ago / 24:.0f} day(s) ago (county 72 h advisory)")
            else:
                recent_rain_penalty = cfg.visibility.rain_recent_penalty_ft
                factors.append(
                    Factor(label="Rain", effect="-", detail=f"{hours_ago / 24:.0f} days ago")
                )
        else:
            factors.append(Factor(label="Rain", effect="+", detail="None in the last few days"))

    # Waves.
    wave_result = cond.waves.get(spot.id)
    waves: WaveSeries | None = (
        wave_result.value if is_fresh(wave_result, "waves", cfg, now) and wave_result else None
    )
    orbital: float | None = None
    if waves and spot.wave_factor < 1:
        waves = sheltered(waves, spot.wave_factor)
        factors.append(
            Factor(
                label="Shelter",
                effect="+",
                detail=f"about {spot.wave_factor:.0%} of the open-coast waves reach here",
            )
        )
    if waves:
        current = latest(waves.obs, now)
        assert current is None or isinstance(current, WaveObs)
        if current is not None:
            sc.hs_ft = round(m_to_ft(current.hs_m), 1)
            sc.tp_s = current.tp_s
            sc.swell_dir_deg = current.dp_deg
            sc.wave_source = waves.source
            limit = spot.thresholds.max_hs_ft
            if waves.source == "mop":
                # MOP is modelled at this spot: compare it directly.
                if sc.hs_ft > limit:
                    gates.append(f"Waves ~{sc.hs_ft:.0f} ft, over {limit:g} ft")
            else:
                # Buoy and model waves are offshore: scale by how exposed the
                # spot is to that direction. The coarse model alone only rules
                # a day out when it's far over the limit; otherwise it's a Maybe.
                at_spot = sc.hs_ft * exposure_weight(
                    current.dp_deg, spot.exposure_deg.exposed, spot.exposure_deg.sheltered
                )
                if waves.source == "openmeteo":
                    limit *= COARSE_MODEL_GATE_FACTOR
                if at_spot > limit:
                    gates.append(
                        f"~{at_spot:.0f} ft of {compass(current.dp_deg)} swell reaching the spot "
                        f"(offshore estimate), over {spot.thresholds.max_hs_ft:g} ft"
                    )
        if waves.source == "openmeteo":
            cautions.append("Waves from a coarse offshore model")
        samples = []
        for o in waves.obs:
            # MOP already accounts for sheltering at the spot; offshore data doesn't.
            weight = (
                1.0
                if waves.source == "mop"
                else exposure_weight(
                    o.dp_deg, spot.exposure_deg.exposed, spot.exposure_deg.sheltered
                )
            )
            if o.energy_m2_hz and waves.freqs_hz and waves.bandwidths_hz:
                # Full spectrum: each band reaches the bottom by its own amount.
                ub = spectral_orbital_velocity(
                    [e * weight**2 for e in o.energy_m2_hz],
                    waves.freqs_hz,
                    waves.bandwidths_hz,
                    spot.bottom_depth_m,
                )
            else:
                ub = bottom_orbital_velocity(
                    o.hs_m * weight, o.tp_s or DEFAULT_TP_S, spot.bottom_depth_m
                )
            samples.append((o.time, ub))
        orbital = decayed_mean(samples, now, cfg.visibility.half_life_h)
        sc.orbital_ms = round(orbital, 3) if orbital is not None else None

    # Wind now (pier measurement, else forecast).
    wind_now: WindObs | None = None
    if is_fresh(cond.wind_obs, "wind", cfg, now) and cond.wind_obs and cond.wind_obs.value:
        obs = latest(cond.wind_obs.value.obs, now)
        wind_now = obs if isinstance(obs, WindObs) else None
    if wind_now is None:
        forecast = cond.wind_forecast.get(spot.id)
        wind_now = wind_near(forecast.value if forecast and forecast.ok else None, now)
    if wind_now is not None:
        sc.wind_kt = round(ms_to_kt(wind_now.speed_ms), 1)
        sc.gust_kt = round(ms_to_kt(wind_now.gust_ms), 1) if wind_now.gust_ms is not None else None
        sc.wind_dir_deg = wind_now.dir_deg
        if wind_now.dir_deg is not None:
            sc.wind_onshore = angle_between(wind_now.dir_deg, spot.shore_normal_deg) <= 60

    # Tide now.
    tides = cond.tides.value if cond.tides and cond.tides.ok and cond.tides.value else None
    if tides:
        height = height_at(tides.points, now)
        sc.tide_ft = round(m_to_ft(height), 1) if height is not None else None
        sc.tide_trend = trend_at(tides.points, now)

    # Best window, and wind across it.
    window = plan_window(spot, cond, cfg, sun_today, sun_tomorrow)
    window_wind = window.max_wind_kt if window.max_wind_kt is not None else sc.wind_kt
    if window_wind is not None and window_wind > spot.thresholds.max_wind_kt:
        gates.append(f"Wind ~{window_wind:.0f} kt even at the best time")

    # Visibility: the turbidity that wave motion and plankton predict (a model
    # fitted to the Scripps Pier sensor), read off the same turbidity-to-feet
    # curve as the sensor itself; recent rain and wind come off after.
    vis: tuple[int, int] | None = None
    vis_mid: float | None = None
    if orbital is not None:
        v = cfg.visibility
        tc = cfg.turbidity
        detail = f"near-bottom motion {orbital:.2f} m/s"
        factors.append(
            Factor(
                label="Swell",
                effect="+" if orbital < 0.2 else "~" if orbital < 0.4 else "-",
                detail=detail,
            )
        )
        chl = cond.chlorophyll
        chl_ug_l = v.typical_chl_ug_l
        if is_fresh(chl, "chlorophyll", cfg, now) and chl and chl.value:
            chl_ug_l = chl.value.chl_ug_l
            factors.append(
                Factor(
                    label="Plankton",
                    effect="-" if chl_ug_l > v.chl_threshold_ug_l else "+",
                    detail=f"chlorophyll {chl_ug_l:.1f} µg/L at the pier",
                )
            )
        penalty = recent_rain_penalty
        if window_wind is not None:
            penalty += v.wind_ft_per_kt * max(0.0, window_wind - v.wind_threshold_kt)
        vis_mid = min(v.max_ft, tc.vis_ft(v.predicted_ntu(orbital, chl_ug_l))) - penalty
        turb = cond.turbidity
        pier_km = distance_km((spot.lat, spot.lon), cfg.pier)
        if pier_km > tc.max_distance_km:
            turb = None  # the pier sensor says nothing about water this far away
        if (
            is_fresh(turb, "turbidity", cfg, now)
            and turb
            and turb.value
            and turb.value.ntu < tc.min_valid_ntu
        ):
            factors.append(
                Factor(
                    label="Turbidity",
                    effect="~",
                    detail=f"pier sensor reads {turb.value.ntu:.2f} NTU, too low to trust; ignored",
                )
            )
        elif is_fresh(turb, "turbidity", cfg, now) and turb and turb.value:
            measured = min(v.max_ft, tc.vis_ft(turb.value.ntu))
            weight = tc.weight_near_pier if spot.near_pier else tc.weight_elsewhere
            vis_mid = weight * measured + (1 - weight) * vis_mid
            factors.append(
                Factor(
                    label="Turbidity",
                    effect="+" if measured >= 15 else "~" if measured >= 8 else "-",
                    detail=f"{turb.value.ntu:.1f} NTU at Scripps Pier (~{measured:.0f} ft)",
                )
            )
        vis_mid = min(v.max_ft, max(v.min_ft, vis_mid))
        spread = vis_mid * v.spread_fraction
        low = max(v.min_ft, round(vis_mid - spread))
        vis = (round(low), round(min(v.max_ft, vis_mid + spread)))

    if window.chosen and window.slots:
        chosen_slots = [
            s for s in window.slots if window.chosen.start <= s.time < window.chosen.end
        ]
        trends = {s.tide_trend for s in chosen_slots}
        if "incoming" in trends:
            factors.append(Factor(label="Tide", effect="+", detail="Incoming during the window"))
        elif "outgoing" in trends:
            factors.append(Factor(label="Tide", effect="-", detail="Outgoing during the window"))
    if window_wind is not None:
        factors.append(
            Factor(
                label="Wind",
                effect="+" if window_wind < 6 else "~" if window_wind < 10 else "-",
                detail=f"~{window_wind:.0f} kt",
            )
        )

    verdict, confidence = _verdict(spot, cfg, gates, cautions, waves, vis, vis_mid, sc, window_wind)
    reason = _reason(verdict, gates, cautions, vis, sc, window)
    return SpotStatus(
        id=spot.id,
        name=spot.name,
        tier=spot.tier,
        difficulty=spot.difficulty,
        area=spot.area,
        verdict=verdict,
        confidence=confidence,
        vis_ft=vis,
        reason=reason,
        window=window.chosen if verdict in ("yes", "maybe") else None,
        window_day=window.day if verdict in ("yes", "maybe") and window.chosen else None,
        gates=gates,
        cautions=cautions,
        factors=factors,
        conditions=sc,
        hourly=window.slots,
        shore_normal_deg=spot.shore_normal_deg,
    )


def _verdict(
    spot: SpotConfig,
    cfg: ScoringConfig,
    gates: list[str],
    cautions: list[str],
    waves: WaveSeries | None,
    vis: tuple[int, int] | None,
    vis_mid: float | None,
    sc: SpotConditions,
    window_wind: float | None,
) -> tuple[Verdict, Confidence]:
    if gates:
        return "no", "high"
    if waves is None or vis is None or vis_mid is None:
        return "unknown", "low"
    if vis[1] < 6:
        return "no", "medium"
    frac = cfg.gates.comfortable_fraction
    comfortable = (sc.hs_ft is not None and sc.hs_ft <= frac * spot.thresholds.max_hs_ft) and (
        window_wind is None or window_wind <= frac * spot.thresholds.max_wind_kt
    )
    confidence: Confidence = "medium" if waves.source in ("mop", "buoy") else "low"
    if vis_mid >= cfg.preferences.min_vis_ft and comfortable and not cautions:
        return "yes", confidence
    return "maybe", "low" if cautions else confidence


def _reason(
    verdict: Verdict,
    gates: list[str],
    cautions: list[str],
    vis: tuple[int, int] | None,
    sc: SpotConditions,
    window: _Window,
) -> str:
    if verdict == "no" and gates:
        return gates[0]
    if verdict == "unknown":
        return "Not enough fresh wave data to call it"
    parts: list[str] = []
    if vis:
        parts.append(f"~{vis[0]}–{vis[1]} ft vis")
    if sc.hs_ft is not None:
        swell = "<1 ft" if sc.hs_ft < 1 else f"{sc.hs_ft:.1f}".removesuffix(".0") + " ft"
        direction = compass(sc.swell_dir_deg)
        period = f" at {sc.tp_s:.0f} s" if sc.tp_s else ""
        parts.append(f"{swell} {direction} swell{period}".replace("  ", " "))
    if window.chosen:
        trends = [
            s.tide_trend for s in window.slots if window.chosen.start <= s.time < window.chosen.end
        ]
        if trends and trends.count("incoming") >= len(trends) / 2:
            parts.append("incoming tide")
    if window.max_wind_kt is not None:
        parts.append(
            "light wind" if window.max_wind_kt < 6 else f"~{window.max_wind_kt:.0f} kt wind"
        )
    if verdict == "no":
        parts.insert(0, "Poor visibility expected")
    line = ", ".join(parts)
    if verdict == "maybe" and cautions:
        line = f"{line} · {cautions[0]}" if line else cautions[0]
    return line
