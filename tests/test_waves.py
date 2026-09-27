from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from snorkel.features.waves import (
    bottom_orbital_velocity,
    decayed_mean,
    exposure_weight,
    wavenumber,
)


@pytest.mark.parametrize(("period", "depth"), [(4, 5), (8, 5), (14, 5), (18, 10), (10, 100)])
def test_wavenumber_solves_dispersion(period: float, depth: float) -> None:
    k = wavenumber(period, depth)
    omega = 2 * math.pi / period
    assert 9.81 * k * math.tanh(k * depth) == pytest.approx(omega**2, rel=1e-9)


def test_deep_water_limit() -> None:
    k = wavenumber(8, 1000)
    assert k == pytest.approx((2 * math.pi / 8) ** 2 / 9.81, rel=1e-6)


def test_long_period_swell_reaches_the_bottom_more() -> None:
    # Same height; the effect grows with depth as short waves stop "feeling" the bottom.
    assert bottom_orbital_velocity(0.6, 15, 5) > 1.25 * bottom_orbital_velocity(0.6, 5, 5)
    assert bottom_orbital_velocity(0.6, 15, 10) > 2 * bottom_orbital_velocity(0.6, 4, 10)
    assert bottom_orbital_velocity(0, 12, 5) == 0


def test_orbital_velocity_magnitude_is_plausible() -> None:
    # ~1 m of 12 s swell over 5 m of water: order 0.5-1 m/s at the bottom.
    assert 0.4 < bottom_orbital_velocity(1.0, 12, 5) < 1.0


def test_exposure_weight_windows() -> None:
    assert exposure_weight(290, (250, 330), (150, 230)) == 1.0
    assert exposure_weight(190, (250, 330), (150, 230)) == 0.2
    assert exposure_weight(240, (250, 330), (150, 230)) == 0.5
    assert exposure_weight(None, (250, 330), None) == 0.5
    assert exposure_weight(5, (340, 20), None) == 1.0  # window wrapping north


def test_decayed_mean_weights_recent_samples_more() -> None:
    now = datetime(2026, 9, 27, 16, tzinfo=UTC)
    samples = [(now - timedelta(hours=48), 10.0), (now, 0.0), (now + timedelta(hours=1), 99.0)]
    value = decayed_mean(samples, now, half_life_h=24)
    assert value == pytest.approx(10 * 0.25 / 1.25)
    assert decayed_mean([], now, 24) is None


def test_spectral_single_band_matches_bulk() -> None:
    from snorkel.features.waves import spectral_orbital_velocity

    hs, period, depth, df = 0.8, 12.0, 5.0, 0.005
    density = (hs / 4) ** 2 / df  # one band holding all the variance: Hs = 4*sqrt(S*df)
    spectral = spectral_orbital_velocity([density], [1 / period], [df], depth)
    assert spectral == pytest.approx(bottom_orbital_velocity(hs, period, depth), rel=1e-9)


def test_spectral_counts_short_chop_less_than_swell() -> None:
    from snorkel.features.waves import spectral_orbital_velocity

    df = 0.01
    swell = spectral_orbital_velocity([1.0], [1 / 14], [df], 8.0)
    chop = spectral_orbital_velocity([1.0], [1 / 4], [df], 8.0)
    assert swell > 2 * chop  # ~2.3x at 8 m for equal surface energy
    assert spectral_orbital_velocity([float("nan"), 0.0], [0.1, 0.2], [df, df], 5) == 0.0


def test_spectral_on_a_real_mop_spectrum() -> None:
    from pathlib import Path

    from snorkel.features.waves import spectral_orbital_velocity
    from snorkel.parse.cdip import parse_waves

    nc = Path(__file__).parent / "fixtures/cdip.mop_nowcast/D0482.nc"
    series = parse_waves(nc.read_bytes(), "mop", "D0482")
    last = series.obs[-1]
    assert last.energy_m2_hz and series.freqs_hz and series.bandwidths_hz
    spectral = spectral_orbital_velocity(
        last.energy_m2_hz, series.freqs_hz, series.bandwidths_hz, 5
    )
    bulk = bottom_orbital_velocity(last.hs_m, last.tp_s or 10, 5)
    # Same sea state, same order of magnitude; the spectrum spreads energy
    # over periods, so it shouldn't match the peak-period shortcut exactly.
    assert 0.1 < spectral < 1.5
    assert 0.5 < spectral / bulk < 1.5
