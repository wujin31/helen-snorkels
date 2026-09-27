"""The pier-cam model on synthetic frames (real frames never enter the repo).

Each frame is water with vignetting and noise, plus four pilings whose
contrast fades as exp(-c * distance), the way it does underwater.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest
from PIL import Image

from snorkel.cv import pier_cam
from snorkel.cv.pier_cam import CamModelConfig, calibrate, read_frame, vis_bin

NOW = datetime(2026, 9, 27, 19, 0, tzinfo=UTC)
W, H = 480, 270
# (x0, width, distance ft): nearer pilings look wider; not in distance order left to right.
PILINGS = [(40, 80, 4.0), (300, 36, 11.0), (200, 24, 14.0), (400, 10, 30.0)]
C0 = -0.9  # a piling's own contrast against the water, up close


def frame(c_per_m: float, shift: int = 0, water: float = 0.35, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    x = np.linspace(-1, 1, W)
    lum = np.tile(water * (1 - 0.25 * x**2), (H, 1))  # vignetting
    for x0, width, distance in PILINGS:
        contrast = C0 * math.exp(-c_per_m * distance / 3.28084)
        a, b = x0 + shift, x0 + shift + width
        lum[int(0.2 * H) :, max(a, 0) : min(b, W)] *= 1 + contrast
    lum = np.clip(lum + rng.normal(0, 0.004, lum.shape), 0, 1)
    srgb = np.where(lum <= 0.0031308, lum * 12.92, 1.055 * lum ** (1 / 2.4) - 0.055)
    gray = (srgb * 255).round().astype(np.uint8)
    return Image.fromarray(np.stack([gray] * 3, axis=-1), "RGB")


@pytest.fixture
def cfg() -> CamModelConfig:
    return pier_cam.load_cam_model()


@pytest.fixture
def rois(cfg: CamModelConfig) -> pier_cam.CamRois:
    return calibrate([frame(0.15, seed=s) for s in range(6)], cfg, NOW)


def test_config_loads_and_stays_private_by_default(cfg: CamModelConfig) -> None:
    assert cfg.piling_distances_ft == [4, 11, 14, 30]
    assert cfg.publish is False


def test_calibration_finds_the_pilings_nearest_first(rois: pier_cam.CamRois) -> None:
    assert [p.distance_ft for p in rois.pilings] == [4, 11, 14, 30]
    for roi, (x0, width, _) in zip(rois.pilings, sorted(PILINGS, key=lambda p: p[2]), strict=True):
        assert x0 <= roi.piling.x0 * W < roi.piling.x1 * W <= x0 + width
    assert len(rois.profile) == pier_cam.PROFILE_POINTS


def test_clear_water_sees_every_piling(rois: pier_cam.CamRois, cfg: CamModelConfig) -> None:
    reading = read_frame(frame(0.15, seed=9), rois, cfg, NOW)
    assert reading.qc is None
    assert reading.pilings_visible == 4 and reading.vis_ft == (30, 40)
    assert reading.beam_c_per_m == pytest.approx(0.15, abs=0.05)


def test_murky_water_loses_the_far_pilings(rois: pier_cam.CamRois, cfg: CamModelConfig) -> None:
    reading = read_frame(frame(0.8, seed=11), rois, cfg, NOW)
    assert reading.qc is None
    assert reading.pilings_visible == 2 and reading.vis_ft == (11, 14)
    assert reading.contrasts[0] < reading.contrasts[1] < 0  # nearest stands out most
    assert reading.beam_c_per_m == pytest.approx(0.8, abs=0.2)


def test_soup_sees_nothing(rois: pier_cam.CamRois, cfg: CamModelConfig) -> None:
    reading = read_frame(frame(3.5, seed=12), rois, cfg, NOW)
    assert reading.pilings_visible == 0 and reading.vis_ft == (0, 4)
    assert reading.beam_c_per_m is None


def test_no_reading_when_dark_frozen_or_moved(rois: pier_cam.CamRois, cfg: CamModelConfig) -> None:
    assert read_frame(frame(0.15, water=0.004), rois, cfg, NOW).qc == "dark"
    assert read_frame(frame(0.15), rois, cfg, NOW, frozen=True).qc == "frozen"
    moved = read_frame(frame(0.15, shift=36, seed=3), rois, cfg, NOW)
    assert moved.qc == "camera moved" and moved.vis_ft is None


def test_a_resized_stream_still_reads(rois: pier_cam.CamRois, cfg: CamModelConfig) -> None:
    bigger = frame(0.15, seed=4).resize((W * 2, H * 2))
    assert read_frame(bigger, rois, cfg, NOW).pilings_visible == 4


def test_vis_bins_follow_the_piling_guide() -> None:
    distances = [4, 11, 14, 30]
    assert [vis_bin(k, distances, 40) for k in range(5)] == [
        (0, 4),
        (4, 11),
        (11, 14),
        (14, 30),
        (30, 40),
    ]


def test_relative_profile_flattens_vignetting() -> None:
    profile = 0.3 * (1 - 0.3 * np.linspace(-1, 1, 200) ** 2)
    profile[90:110] *= 0.5
    rel = pier_cam.relative_profile(profile)
    assert abs(rel[:80]).max() < 0.01 and abs(rel[120:]).max() < 0.01
    assert rel[100] == pytest.approx(-0.5, abs=0.02)
