"""The day-one archiver: capture every due source and store it untouched.

Each run:
1. reads today's and yesterday's manifest to see when each source last ran;
2. for every source that is due (cadence elapsed, daylight if required, not
   switched off), calls its capture function with a timeout;
3. stores each item (gzipped raw bytes, or a JPEG frame) and appends one
   manifest row per item, including failures.

A failing or hanging source is recorded and skipped; it never stops the run.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import threading
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any, TypeVar

import httpx

from snorkel.config import load_sources, load_spots
from snorkel.fetch import SOURCES
from snorkel.fetch.base import FetchContext, ItemError, SkipSource, SourceFn, describe_error, slug
from snorkel.http import make_client
from snorkel.models import CaptureRecord, SourcesConfig, SpotConfig
from snorkel.storage import Storage
from snorkel.sun import sun_elevation

T = TypeVar("T")

WRITER = "archive"
DEFAULT_TIMEOUT_S = 120.0
FALSY = {"0", "false", "no", "off"}
CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "json": "application/json",
    "csv": "text/csv",
    "txt": "text/plain",
    "html": "text/html",
    "nc": "application/x-netcdf",
}


def manifest_key(day: date, writer: str = WRITER) -> str:
    return f"manifest/{day.isoformat()}/{writer}.jsonl"


def snapshot_key(source: str, variant: str | None, when: datetime, ext: str) -> str:
    name = when.strftime("%H%M%SZ") + (f"_{slug(variant)}" if variant else "")
    day = when.strftime("%Y/%m/%d")
    if ext == "jpg":
        return f"frames/{source}/{day}/{name}.jpg"
    return f"raw/{source}/{day}/{name}.{ext}.gz"


def read_manifest(storage: Storage, day: date, writer: str = WRITER) -> list[CaptureRecord]:
    data = storage.get(manifest_key(day, writer))
    if not data:
        return []
    records = []
    for line in data.decode().splitlines():
        if not line.strip():
            continue
        try:
            records.append(CaptureRecord.model_validate_json(line))
        except ValueError:
            continue  # a corrupt line shouldn't block the archive
    return records


def append_manifest(
    storage: Storage, day: date, records: list[CaptureRecord], writer: str = WRITER
) -> None:
    if not records:
        return
    existing = storage.get(manifest_key(day, writer)) or b""
    if existing and not existing.endswith(b"\n"):
        existing += b"\n"
    lines = "".join(r.model_dump_json(exclude_none=True) + "\n" for r in records)
    storage.put(manifest_key(day, writer), existing + lines.encode(), "application/x-ndjson")


def is_due(previous: list[CaptureRecord], every_minutes: int, now: datetime) -> bool:
    """Due when `every_minutes` have passed since the last ok/skipped attempt.

    Errors don't count as attempts, so a failed source retries next run.
    A little slack absorbs cron jitter (GitHub schedules drift by minutes).
    """
    attempts = [r.run_at for r in previous if r.status in ("ok", "skipped")]
    if not attempts:
        return True
    slack = timedelta(minutes=min(5.0, every_minutes / 3))
    return now - max(attempts) >= timedelta(minutes=every_minutes) - slack


def env_disabled(params: Mapping[str, Any], environ: Mapping[str, str]) -> bool:
    name = params.get("enabled_env")
    return bool(name) and environ.get(str(name), "").strip().lower() in FALSY


def run_with_timeout(fn: Callable[[], T], timeout_s: float) -> T:
    """Run `fn` in a daemon thread so a hung download can't stall the whole run."""
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller's thread
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        raise TimeoutError(f"timed out after {timeout_s:g}s")
    if "error" in result:
        raise result["error"]
    return result["value"]


def run_archive(
    storage: Storage,
    *,
    now: datetime,
    only: list[str] | None = None,
    force: bool = False,
    client: httpx.Client | None = None,
    spots: list[SpotConfig] | None = None,
    sources: SourcesConfig | None = None,
    registry: Mapping[str, SourceFn] | None = None,
    environ: Mapping[str, str] | None = None,
    log: Callable[[str], None] = print,
) -> list[CaptureRecord]:
    """Capture every due source once. `force` ignores cadence and daylight."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    spots = spots if spots is not None else load_spots()
    sources = sources or load_sources()
    registry = registry if registry is not None else SOURCES
    environ = environ if environ is not None else os.environ
    unknown = set(only or []) - set(registry)
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(sorted(unknown))}")

    today = now.date()
    history = read_manifest(storage, today - timedelta(days=1)) + read_manifest(storage, today)
    own_client = client is None
    client = client or make_client()
    records: list[CaptureRecord] = []
    try:
        for source_id, capture in registry.items():
            if only and source_id not in only:
                continue
            params = sources.sources.get(source_id)
            if params is None:
                log(f"  {source_id}: no config, skipping")
                continue
            if env_disabled(params, environ):
                log(f"  {source_id}: disabled by ${params['enabled_env']}")
                continue
            previous = [r for r in history if r.source == source_id]
            if not force and not is_due(previous, int(params["every_minutes"]), now):
                continue
            min_sun = params.get("min_sun_elevation_deg")
            if not force and min_sun is not None:
                elevation = sun_elevation(sources.location.lat, sources.location.lon, now)
                if elevation < float(min_sun):
                    log(f"  {source_id}: sun at {elevation:.1f}°, below {min_sun}°")
                    continue
            ctx = FetchContext(
                client=client,
                now=now,
                spots=spots,
                params=params,
                location=sources.location,
                previous=previous,
            )
            timeout = float(params.get("timeout_s", DEFAULT_TIMEOUT_S))
            records += _capture_source(storage, source_id, capture, ctx, timeout)
    finally:
        if own_client:
            client.close()
    append_manifest(storage, today, records)
    return records


def _capture_source(
    storage: Storage, source_id: str, capture: SourceFn, ctx: FetchContext, timeout_s: float
) -> list[CaptureRecord]:
    now = ctx.now
    try:
        items = run_with_timeout(lambda: capture(ctx), timeout_s)
    except SkipSource as exc:
        return [CaptureRecord(source=source_id, run_at=now, status="skipped", error=str(exc))]
    except Exception as exc:
        return [
            CaptureRecord(source=source_id, run_at=now, status="error", error=describe_error(exc))
        ]

    records: list[CaptureRecord] = []
    for item in items:
        if isinstance(item, ItemError):
            records.append(
                CaptureRecord(
                    source=source_id,
                    variant=item.variant,
                    run_at=now,
                    status="error",
                    url=item.url,
                    error=item.error,
                )
            )
            continue
        key = snapshot_key(source_id, item.variant, now, item.ext)
        body = item.content if item.ext == "jpg" else gzip.compress(item.content, mtime=0)
        content_type = "application/gzip" if item.ext != "jpg" else CONTENT_TYPES["jpg"]
        record = CaptureRecord(
            source=source_id,
            variant=item.variant,
            run_at=now,
            status="ok",
            url=item.url,
            key=key,
            bytes=len(item.content),
            sha256=hashlib.sha256(item.content).hexdigest(),
            meta=item.meta,
        )
        try:
            storage.put(key, body, content_type)
        except Exception as exc:
            record = record.model_copy(
                update={"status": "error", "key": None, "error": f"store: {describe_error(exc)}"}
            )
        records.append(record)
    return records
