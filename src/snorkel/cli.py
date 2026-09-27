"""Command line: `uv run snorkel --help`."""

from __future__ import annotations

import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from snorkel.archive import run_archive
from snorkel.config import load_sources, load_spots
from snorkel.fetch import SOURCES
from snorkel.fetch.base import FetchContext, ItemError, SkipSource
from snorkel.http import make_client
from snorkel.models import CaptureRecord
from snorkel.storage import storage_from_spec

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _summary(records: list[CaptureRecord]) -> str:
    counts = Counter(r.status for r in records)
    lines = [
        f"{len(records)} item(s): {counts['ok']} ok, {counts['error']} error, "
        f"{counts['skipped']} skipped",
        "",
        "| source | variant | status | bytes | detail |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        detail = r.error or r.key or ""
        qc = {k: r.meta[k] for k in ("strategy", "brightness", "frozen", "rows") if k in r.meta}
        if qc:
            detail += f" {qc}"
        detail = detail.replace("|", "/")[:200]
        lines.append(
            f"| {r.source} | {r.variant or ''} | {r.status} | {r.bytes or ''} | {detail} |"
        )
    return "\n".join(lines)


@app.command()
def archive(
    storage: Annotated[
        str | None,
        typer.Option(
            help="local:<dir> or s3[:<bucket>]. Default: $SNORKEL_STORAGE or local:.archive"
        ),
    ] = None,
    only: Annotated[list[str] | None, typer.Option(help="Capture only these source ids")] = None,
    force: Annotated[bool, typer.Option(help="Ignore cadence and daylight gating")] = False,
    now: Annotated[
        str | None, typer.Option(help="Pretend it's this ISO time (UTC default)")
    ] = None,
) -> None:
    """Capture every due source into the archive."""
    target = storage_from_spec(storage)
    print(f"archive -> {target.describe()}")
    records = run_archive(target, now=_parse_now(now), only=only or None, force=force)
    summary = _summary(records)
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as fh:
            fh.write("## Archive run\n\n" + summary + "\n")
    # Individual source failures are expected and recorded; only fail the run
    # when nothing at all worked, which usually means storage or network is down.
    if records and all(r.status == "error" for r in records):
        raise typer.Exit(1)


@app.command("check-storage")
def check_storage(
    storage: Annotated[
        str | None,
        typer.Option(help="local:<dir>, gateway:<url> or s3[:<bucket>]. Default: $SNORKEL_STORAGE"),
    ] = None,
) -> None:
    """Write, read back, and miss one object to prove storage works end to end."""
    target = storage_from_spec(storage)
    key = "state/healthcheck/latest.txt"
    payload = f"ok {datetime.now(UTC).isoformat()}".encode()
    target.put(key, payload, "text/plain")
    read_back = target.get(key)
    missing = target.get("state/healthcheck/never-written.txt")
    print(f"{target.describe()}: wrote {key}, read back {read_back!r}, missing -> {missing!r}")
    if read_back != payload or missing is not None:
        raise typer.Exit(1)


@app.command()
def probe(
    source: Annotated[str, typer.Argument(help="Source id, e.g. tides.observed")],
    save_fixture: Annotated[
        bool, typer.Option(help="Write each item to tests/fixtures/<source>/")
    ] = False,
    fixtures_dir: Annotated[Path, typer.Option()] = Path("tests/fixtures"),
) -> None:
    """Run one source now (no cadence, no storage) and show what came back."""
    if source not in SOURCES:
        raise typer.BadParameter(f"unknown source; choose from: {', '.join(SOURCES)}")
    sources = load_sources()
    with make_client() as client:
        ctx = FetchContext(
            client=client,
            now=datetime.now(UTC),
            spots=load_spots(),
            params=sources.sources.get(source, {}),
            location=sources.location,
        )
        try:
            items = SOURCES[source](ctx)
        except SkipSource as exc:
            print(f"skipped: {exc}")
            return
    for item in items:
        if isinstance(item, ItemError):
            print(f"ERROR {item.variant or ''} {item.url}\n  {item.error}")
            continue
        print(f"OK {item.variant or ''} {item.url} ({len(item.content)} bytes) meta={item.meta}")
        if item.ext in ("json", "csv", "txt", "html"):
            print("  " + item.content[:400].decode("utf-8", errors="replace").replace("\n", "\n  "))
        if save_fixture:
            path = fixtures_dir / source / f"{item.variant or 'item'}.{item.ext}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(item.content)
            print(f"  saved {path}")


@app.command()
def score(
    out: Annotated[Path, typer.Option(help="Where to write status.json")] = Path("status.json"),
    history: Annotated[
        Path | None, typer.Option(help="Append one row per spot to this JSONL file")
    ] = None,
    now: Annotated[
        str | None, typer.Option(help="Pretend it's this ISO time (UTC default)")
    ] = None,
    storage: Annotated[
        str | None,
        typer.Option(help="Archive to fall back on for CDIP. Default: $SNORKEL_STORAGE, if set"),
    ] = None,
) -> None:
    """Fetch fresh conditions, score every spot, write status.json."""
    import json

    from snorkel.pipeline import gather
    from snorkel.publish.status import history_rows
    from snorkel.score.config import load_scoring
    from snorkel.score.run import score_all

    when = _parse_now(now)
    spots, sources, cfg = load_spots(), load_sources(), load_scoring()
    archive = None
    spec = storage or os.environ.get("SNORKEL_STORAGE")
    if spec:
        try:
            archive = storage_from_spec(spec)
        except Exception as exc:  # scoring must not depend on the archive
            print(f"archive fallback unavailable: {exc}")
    with make_client() as client:
        cond = gather(client, when, spots, sources, storage=archive)
    doc = score_all(cond, spots, sources, cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc.model_dump_json(indent=1))
    print(doc.summary)
    for spot in doc.spots:
        print(f"  {spot.name}: {spot.verdict} ({spot.confidence}) · {spot.reason}")
    for health in doc.sources:
        if health.stale:
            print(f"  stale: {health.label}: {health.error or 'old data'}")
    if history:
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a") as fh:
            for row in history_rows(doc):
                fh.write(json.dumps(row) + "\n")


@app.command("discover-mops")
def discover_mops(
    window: Annotated[int, typer.Option(help="MOPs to scan either side of the bisection")] = 20,
) -> None:
    """Find the CDIP MOP alongshore points nearest each configured spot."""
    from snorkel.discover import list_mop_ids, nearest_mops, read_mop_site

    with make_client() as client:
        ids = list_mop_ids(client)
    print(f"{len(ids)} MOP nowcast files ({ids[0]}..{ids[-1]})" if ids else "no MOP files found")
    for spot in load_spots():
        print(f"\n{spot.id} ({spot.lat}, {spot.lon}):")
        for site in nearest_mops(spot.lat, spot.lon, ids, read_mop_site, window=window):
            km = site.distance_km(spot.lat, spot.lon)
            print(f"  {site.id}  {site.lat:.5f}, {site.lon:.5f}  {km:.2f} km  {site.meta}")


@app.command()
def sniff(
    url: Annotated[str, typer.Argument(help="Page to load headlessly")],
    wait: Annotated[float, typer.Option(help="Seconds to keep listening")] = 20,
) -> None:
    """List every request a page makes (find hidden JSON/API and stream URLs)."""
    from snorkel.discover import sniff_requests

    for resource_type, method, request_url in sniff_requests(url, wait):
        if resource_type not in {"image", "font", "stylesheet"}:
            print(f"{resource_type:10} {method:5} {request_url}")


if __name__ == "__main__":
    app()
