"""The pier-cam model against the private archive: calibrate, read, remember.

Frames, piling positions and readings all stay in the archive (`frames/`,
`state/cam_rois.json`, `state/cam_readings/`). Nothing here prints or
publishes a reading; whether one reaches the page is `CamModelConfig.publish`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from snorkel.archive import read_manifest
from snorkel.cv.pier_cam import CamModelConfig, CamRois, FrameReading, calibrate, load_image
from snorkel.cv.pier_cam import read_frame as read_image
from snorkel.models import CaptureRecord
from snorkel.storage import Storage

CAM_SOURCE = "cam.scripps_pier"
ROIS_KEY = "state/cam_rois.json"
FRESH_FRAME = timedelta(minutes=30)  # an older frame is no reading of "now"


def readings_key(day: date) -> str:
    return f"state/cam_readings/{day.isoformat()}.jsonl"


def frame_records(storage: Storage, now: datetime, days: int = 1) -> list[CaptureRecord]:
    """Archived cam frames from the last `days` days (plus today), oldest first."""
    records: list[CaptureRecord] = []
    for back in range(days, -1, -1):
        records += read_manifest(storage, now.date() - timedelta(days=back))
    frames = [r for r in records if r.source == CAM_SOURCE and r.status == "ok" and r.key]
    return sorted((r for r in frames if r.run_at <= now), key=lambda r: r.run_at)


def load_rois(storage: Storage) -> CamRois | None:
    data = storage.get(ROIS_KEY)
    return CamRois.model_validate_json(data) if data else None


def calibration_candidates(
    records: list[CaptureRecord], cfg: CamModelConfig
) -> list[CaptureRecord]:
    """Bright, moving, well-lit frames, newest first."""
    good = [
        r
        for r in records
        if not r.meta.get("frozen")
        and float(r.meta.get("sun_elevation", 0)) >= cfg.calibration.min_sun_elevation_deg
        and float(r.meta.get("brightness", 0)) >= cfg.min_brightness
    ]
    return sorted(good, key=lambda r: r.run_at, reverse=True)[: cfg.calibration.candidates]


def recalibrate(storage: Storage, cfg: CamModelConfig, now: datetime) -> CamRois | None:
    records = frame_records(storage, now, days=cfg.calibration.days)
    images = []
    for record in calibration_candidates(records, cfg):
        assert record.key is not None
        data = storage.get(record.key)
        if data:
            images.append(load_image(data))
    if not images:
        return None
    rois = calibrate(images, cfg, now)
    storage.put(ROIS_KEY, rois.model_dump_json().encode(), "application/json")
    return rois


def ensure_rois(storage: Storage, cfg: CamModelConfig, now: datetime) -> CamRois | None:
    """Current piling positions; recalibrates weekly, or daily while some are missing."""
    rois = load_rois(storage)
    if rois is None:
        return recalibrate(storage, cfg, now)
    age = now - rois.calibrated_at
    incomplete = len(rois.pilings) < len(cfg.piling_distances_ft)
    old = age > timedelta(days=cfg.calibration.max_age_days)
    if old or (incomplete and age > timedelta(days=1)):
        return recalibrate(storage, cfg, now) or rois
    return rois


def read_logged(storage: Storage, day: date) -> list[FrameReading]:
    data = storage.get(readings_key(day))
    if not data:
        return []
    out = []
    for line in data.decode().splitlines():
        if line.strip():
            try:
                out.append(FrameReading.model_validate_json(line))
            except ValueError:
                continue
    return out


def _log(storage: Storage, day: date, readings: list[FrameReading]) -> None:
    existing = storage.get(readings_key(day)) or b""
    if existing and not existing.endswith(b"\n"):
        existing += b"\n"
    lines = "".join(r.model_dump_json(exclude_none=True) + "\n" for r in readings)
    storage.put(readings_key(day), existing + lines.encode(), "application/x-ndjson")


def catch_up(
    storage: Storage, cfg: CamModelConfig, now: datetime, limit: int = 16
) -> FrameReading | None:
    """Read every recent frame not yet in the private log; return the newest if fresh.

    Each frame is read once, whatever the scoring cadence.
    """
    records = frame_records(storage, now)[-limit:]
    if not records:
        return None
    logged: dict[str | None, FrameReading] = {}
    for day in sorted({r.run_at.date() for r in records}):
        logged.update({r.frame_key: r for r in read_logged(storage, day)})
    todo = [r for r in records if r.key not in logged]
    rois = ensure_rois(storage, cfg, now) if todo else None
    fresh: dict[date, list[FrameReading]] = {}
    for record in todo:
        if rois is None:
            break
        assert record.key is not None
        data = storage.get(record.key)
        if data is None:
            continue
        motion = record.meta.get("motion")
        reading = read_image(
            load_image(data),
            rois,
            cfg,
            record.run_at,
            frame_key=record.key,
            frozen=bool(record.meta.get("frozen")),
            motion=float(motion) if motion is not None else None,
        )
        fresh.setdefault(record.run_at.date(), []).append(reading)
        logged[record.key] = reading
    for day, readings in fresh.items():
        _log(storage, day, readings)
    latest = records[-1]
    return logged.get(latest.key) if now - latest.run_at <= FRESH_FRAME else None
