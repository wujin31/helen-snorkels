"""Visibility from the Scripps Pier underwater cam, without anyone looking at frames.

The Shore Stations' piling guide puts pilings 4, 11, 14 and 30 ft from the
camera; the farthest one you can still make out brackets the visibility.

Calibration finds the pilings on its own: in a median of clear daylight
frames, each piling is a dark vertical band against the water. Nearer pilings
look wider, so bands sorted by width map to the guide's distances. A reading
then measures each piling's Weber contrast against the water trend at its
own columns (a smooth fit through the open-water columns, so vignetting and
light falloff cancel), on linear luminance. Contrast fades as exp(-c * distance) with the beam
attenuation c (Duntley), so the fade across pilings also gives c, and
horizontal visibility is about 4.8 / c (the black-disk rule).

Everything here is pure: bytes and numbers in, numbers out.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, Field

from snorkel.config import config_dir
from snorkel.units import m_to_ft

Array = NDArray[np.float64]
PROFILE_POINTS = 96  # calibration profile kept for the camera-moved check


class CalibrationConfig(BaseModel):
    days: int = 7
    candidates: int = 60
    frames: int = 20
    min_sun_elevation_deg: float = 15
    max_age_days: float = 7


class CamModelConfig(BaseModel):
    piling_distances_ft: list[float] = Field(default_factory=lambda: [4, 11, 14, 30])
    max_vis_ft: int = 40
    rows: tuple[float, float] = (0.35, 0.95)
    min_band_depth: float = 0.08
    min_band_width: float = 0.008
    visible_contrast: float = 0.05
    min_brightness: float = 25
    moved_shift: float = 0.03
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    publish: bool = False


def load_cam_model(path: Path | None = None) -> CamModelConfig:
    path = path or config_dir() / "cam_model.yaml"
    return CamModelConfig.model_validate(yaml.safe_load(path.read_text()))


class Box(BaseModel):
    """A rectangle as fractions of the frame (0-1), so frame size can change."""

    x0: float
    y0: float
    x1: float
    y1: float

    def pixels(self, width: int, height: int) -> tuple[slice, slice]:
        x0, x1 = round(self.x0 * width), max(round(self.x1 * width), round(self.x0 * width) + 1)
        y0, y1 = round(self.y0 * height), max(round(self.y1 * height), round(self.y0 * height) + 1)
        return slice(y0, y1), slice(x0, x1)


class PilingRoi(BaseModel):
    distance_ft: float
    piling: Box
    depth: float  # how much darker than the water trend it was at calibration


class CamRois(BaseModel):
    """Where the pilings are, found by `calibrate`. Lives in the private archive."""

    calibrated_at: datetime
    frames: int
    width: int
    height: int
    pilings: list[PilingRoi]  # nearest first
    profile: list[float]  # relative column profile at calibration, PROFILE_POINTS long


class FrameReading(BaseModel):
    """One frame's reading. `qc` names why there's no reading (dark, frozen, moved...)."""

    time: datetime
    frame_key: str | None = None
    qc: str | None = None
    brightness: float | None = None
    motion: float | None = None
    contrasts: list[float] = Field(default_factory=list)  # nearest piling first
    pilings_visible: int | None = None
    pilings_total: int | None = None
    vis_ft: tuple[int, int] | None = None
    beam_c_per_m: float | None = None
    vis_physics_ft: float | None = None


# --- image basics -----------------------------------------------------------


def linear_luminance(image: Image.Image) -> Array:
    """Relative luminance (0-1) on linear light, from an sRGB image."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64) / 255.0
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def load_image(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert("RGB")


def brightness(image: Image.Image) -> float:
    return float(np.asarray(image.convert("L"), dtype=np.float64).mean())


def column_profile(lum: Array, rows: tuple[float, float]) -> Array:
    height = lum.shape[0]
    return lum[round(rows[0] * height) : round(rows[1] * height)].mean(axis=0)


def relative_profile(profile: Array, iterations: int = 6) -> Array:
    """Each column's brightness relative to the water trend (0 = water, <0 = darker).

    The trend is a quadratic (vignetting, light falloff) fitted to the columns
    that aren't dark bands, found by repeatedly clipping the darkest.
    """
    x = np.linspace(-1.0, 1.0, profile.size)
    keep = np.ones(profile.size, dtype=bool)
    trend = np.full(profile.size, float(profile.mean()))
    for _ in range(iterations):
        coeffs = np.polyfit(x[keep], profile[keep], 2)
        trend = np.polyval(coeffs, x)
        resid = profile - trend
        spread = float(np.median(np.abs(resid[keep] - np.median(resid[keep])))) * 1.4826
        keep = resid > -2.5 * max(spread, 1e-6)
        if keep.sum() < profile.size * 0.3:
            break
    return profile / np.maximum(trend, 1e-6) - 1.0


# --- calibration ---------------------------------------------------------------


class Band(BaseModel):
    x0: int
    x1: int
    depth: float

    @property
    def width(self) -> int:
        return self.x1 - self.x0


def find_bands(rel: Array, min_depth: float, min_width: int, merge_gap: int = 3) -> list[Band]:
    dark = rel < -min_depth
    runs: list[list[int]] = []
    x = 0
    while x < rel.size:
        if dark[x]:
            start = x
            while x < rel.size and dark[x]:
                x += 1
            if runs and start - runs[-1][1] <= merge_gap:
                runs[-1][1] = x
            else:
                runs.append([start, x])
        else:
            x += 1
    return [Band(x0=a, x1=b, depth=float(-rel[a:b].min())) for a, b in runs if b - a >= min_width]


def _shrink(band: Band, width: int, cfg: CamModelConfig) -> Box:
    inset = band.width * 0.2
    return Box(
        x0=(band.x0 + inset) / width,
        y0=cfg.rows[0],
        x1=(band.x1 - inset) / width,
        y1=cfg.rows[1],
    )


def _resample(profile: Array, points: int = PROFILE_POINTS) -> list[float]:
    x = np.linspace(0, profile.size - 1, points)
    return [round(float(v), 4) for v in np.interp(x, np.arange(profile.size), profile)]


def calibrate(frames: list[Image.Image], cfg: CamModelConfig, now: datetime) -> CamRois:
    """Find the pilings in the clearest of `frames` (same camera, daylight)."""
    if not frames:
        raise ValueError("no frames to calibrate from")
    size = frames[0].size
    rels = []
    for frame in frames:
        if frame.size != size:
            frame = frame.resize(size)
        rels.append(relative_profile(column_profile(linear_luminance(frame), cfg.rows)))
    # The clearest frames have the most structure; their median is the steadiest.
    clearest = sorted(rels, key=lambda r: float(r.std()), reverse=True)[: cfg.calibration.frames]
    rel = np.median(np.stack(clearest), axis=0)
    width, height = size
    bands = find_bands(rel, cfg.min_band_depth, max(2, round(cfg.min_band_width * width)))
    count = len(cfg.piling_distances_ft)
    strongest = sorted(bands, key=lambda b: b.depth * b.width, reverse=True)[:count]
    by_width = sorted(strongest, key=lambda b: b.width, reverse=True)  # nearer looks wider
    pilings = [
        PilingRoi(
            distance_ft=distance,
            piling=_shrink(band, width, cfg),
            depth=round(band.depth, 4),
        )
        for band, distance in zip(by_width, sorted(cfg.piling_distances_ft), strict=False)
    ]
    return CamRois(
        calibrated_at=now,
        frames=len(clearest),
        width=width,
        height=height,
        pilings=pilings,
        profile=_resample(rel),
    )


# --- readings ---------------------------------------------------------------------


def vis_bin(visible: int, distances: Sequence[float], max_vis_ft: int) -> tuple[int, int]:
    """The guide's bracket: seeing the k nearest pilings means between the kth and next."""
    edges = [0, *(int(d) for d in sorted(distances)), max_vis_ft]
    k = max(0, min(visible, len(edges) - 2))
    return edges[k], edges[k + 1]


def beam_attenuation(contrasts: list[float], distances_ft: list[float]) -> float | None:
    """c (1/m) from how piling contrast fades with distance; needs two seen pilings."""
    points = [
        (d / 3.28084, math.log(-c))
        for c, d in zip(contrasts, distances_ft, strict=False)
        if c < 0 and -c < 1.5
    ]
    if len(points) < 2:
        return None
    x = np.array([p[0] for p in points])
    y = np.array([p[1] for p in points])
    if float(np.ptp(x)) <= 0:
        return None
    slope = float(np.polyfit(x, y, 1)[0])
    return -slope if slope < 0 else None


def camera_moved(rel: Array, rois: CamRois, cfg: CamModelConfig) -> bool:
    """True when today's piling pattern lines up with calibration only after a shift."""
    now = np.array(_resample(rel))
    then = np.array(rois.profile)
    if float(now.std()) < 1e-3 or float(then.std()) < 1e-3:
        return False
    max_shift = max(1, round(0.15 * PROFILE_POINTS))
    best, best_score = 0, -np.inf
    for shift in range(-max_shift, max_shift + 1):
        a = now[max(0, shift) : PROFILE_POINTS + min(0, shift)]
        b = then[max(0, -shift) : PROFILE_POINTS + min(0, -shift)]
        score = float(np.corrcoef(a, b)[0, 1])
        if score > best_score:
            best, best_score = shift, score
    return best_score > 0.5 and abs(best) / PROFILE_POINTS > cfg.moved_shift


def read_frame(
    image: Image.Image,
    rois: CamRois,
    cfg: CamModelConfig,
    time: datetime,
    frame_key: str | None = None,
    frozen: bool = False,
    motion: float | None = None,
) -> FrameReading:
    reading = FrameReading(
        time=time,
        frame_key=frame_key,
        brightness=round(brightness(image), 1),
        motion=motion,
        pilings_total=len(rois.pilings),
    )
    if frozen:
        return reading.model_copy(update={"qc": "frozen"})
    if (reading.brightness or 0) < cfg.min_brightness:
        return reading.model_copy(update={"qc": "dark"})
    if not rois.pilings:
        return reading.model_copy(update={"qc": "no pilings calibrated"})
    if image.size != (rois.width, rois.height):
        image = image.resize((rois.width, rois.height))
    rel = relative_profile(column_profile(linear_luminance(image), cfg.rows))
    contrasts = []
    for roi in rois.pilings:
        _, cols = roi.piling.pixels(rois.width, rois.height)
        contrasts.append(round(float(rel[cols].mean()), 4))
    seen = [c <= -cfg.visible_contrast for c in contrasts]
    visible = next((i for i, s in enumerate(seen) if not s), len(seen))  # contiguous from nearest
    if seen[0] and camera_moved(rel, rois, cfg):
        return reading.model_copy(update={"qc": "camera moved", "contrasts": contrasts})
    distances = [p.distance_ft for p in rois.pilings]
    c = beam_attenuation(contrasts[: max(visible, 0)], distances[:visible])
    return reading.model_copy(
        update={
            "contrasts": contrasts,
            "pilings_visible": visible,
            "vis_ft": vis_bin(visible, cfg.piling_distances_ft, cfg.max_vis_ft),
            "beam_c_per_m": round(c, 4) if c else None,
            "vis_physics_ft": round(m_to_ft(4.8 / c), 1) if c else None,
        }
    )
