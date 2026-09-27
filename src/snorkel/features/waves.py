"""Wave physics: how much wave motion reaches the bottom at a snorkel spot.

Visibility drops when wave orbital motion stirs sediment off the bottom, and
long-period swell reaches the bottom far more than short chop of the same
height. v0 uses a bulk (Hs, Tp) linear-theory estimate; Phase 4 replaces it
with the full spectral sum from archived CDIP spectra.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

G = 9.81


def wavenumber(period_s: float, depth_m: float) -> float:
    """Solve the linear dispersion relation w^2 = g k tanh(k h) for k (rad/m)."""
    if period_s <= 0 or depth_m <= 0:
        raise ValueError("period and depth must be positive")
    omega = 2 * math.pi / period_s
    # Fenton & McKee (1990) explicit approximation, then Newton polish.
    k0 = omega**2 / G
    k = k0 / math.tanh((k0 * depth_m) ** 0.75) ** (2 / 3)
    for _ in range(3):
        f = G * k * math.tanh(k * depth_m) - omega**2
        df = G * math.tanh(k * depth_m) + G * k * depth_m / math.cosh(k * depth_m) ** 2
        k -= f / df
    return k


def bottom_orbital_velocity(hs_m: float, tp_s: float, depth_m: float) -> float:
    """Near-bottom orbital velocity amplitude (m/s) for a wave of height Hs, period Tp.

    u_b = pi * H / (T * sinh(k h))
    """
    if hs_m <= 0:
        return 0.0
    k = wavenumber(tp_s, depth_m)
    return math.pi * hs_m / (tp_s * math.sinh(k * depth_m))


def exposure_weight(
    direction_deg: float | None,
    exposed: tuple[float, float],
    sheltered: tuple[float, float] | None,
) -> float:
    """How much swell from `direction_deg` (coming-from, true) reaches the spot.

    1 inside the exposed window, 0.2 inside the sheltered window, 0.5 in
    between or when the direction is unknown. Priors to validate.
    """
    if direction_deg is None:
        return 0.5
    if _within(direction_deg, exposed):
        return 1.0
    if sheltered and _within(direction_deg, sheltered):
        return 0.2
    return 0.5


def _within(direction: float, window: tuple[float, float]) -> bool:
    lo, hi = window[0] % 360, window[1] % 360
    d = direction % 360
    return lo <= d <= hi if lo <= hi else d >= lo or d <= hi


def decayed_mean(
    samples: Sequence[tuple[datetime, float]],
    now: datetime,
    half_life_h: float,
) -> float | None:
    """Exponentially time-weighted mean of past samples (future ones ignored).

    Visibility has memory: yesterday's swell still clouds the water today.
    """
    num = den = 0.0
    for when, value in samples:
        age_h = (now - when).total_seconds() / 3600
        if age_h < 0:
            continue
        weight = 0.5 ** (age_h / half_life_h)
        num += weight * value
        den += weight
    return num / den if den else None
