"""One still frame from the Scripps Pier underwater cam.

Access is deliberately light: one frame per archive run (every 15 min in
daylight), never a continuous stream. Frames stay in the private bucket and
aren't republished until the Shore Stations team says that's OK
(docs/scripps-cam-request.md). The repo variable CAM_CAPTURE_ENABLED=false
stops capture without a code change.

Strategies, in order of preference:
1. `snapshot_url`: a published still, if one exists (lightest on everyone).
2. HLS: `hls_url`, or the .m3u8 in HDOnTap's public player page (`page_url`);
   ffmpeg decodes a few frames from the segment it downloads anyway (no extra
   requests). Their median is the archived still, free of passing fish and
   particles, and the change between them measures surge. Requests say who
   we are and where we came from; nothing pretends to be another site.
3. Browser: headless Chromium loads the public page, watches its network
   requests for the stream URL (then ffmpeg), or screenshots the <video>.
"""

from __future__ import annotations

import html
import io
import re
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageStat

from snorkel.fetch.base import (
    FetchContext,
    Item,
    ItemError,
    RawSnapshot,
    describe_error,
    unique,
)
from snorkel.http import get_with_retry, user_agent
from snorkel.sun import sun_elevation

M3U8_RE = re.compile(r"""https?://[^\s"'<>\\]+?\.m3u8[^\s"'<>\\]*""")
FROZEN_MAX_BITS = 2  # dHash distance at or below which two frames count as identical
FROZEN_WINDOW = timedelta(minutes=60)
# Mean absolute change (0-255 grey levels) between consecutive frames below
# which a clip counts as frozen. Live water always has particles and noise.
FROZEN_MOTION = 0.05


UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def find_m3u8(page_html: str) -> list[str]:
    """Stream URLs in a page, including JSON-escaped ones (\\/ and \\u0026)."""
    text = UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), page_html)
    text = html.unescape(text.replace("\\/", "/"))
    return unique(M3U8_RE.findall(text))


def dhash(gray: Image.Image, size: int = 8) -> str:
    """64-bit difference hash, for spotting a frozen stream."""
    small = gray.resize((size + 1, size), Image.Resampling.BILINEAR)
    pixels = small.tobytes()
    bits = 0
    for row in range(size):
        for col in range(size):
            left = pixels[row * (size + 1) + col]
            right = pixels[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def process_frame(raw: bytes, width: int, quality: int) -> tuple[bytes, dict[str, Any]]:
    """Downscale to `width`, re-encode as JPEG, and compute cheap QC stats."""
    image = Image.open(io.BytesIO(raw))
    image.load()
    image = image.convert("RGB")
    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    gray = image.convert("L")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality, optimize=True)
    meta = {
        "width": image.width,
        "height": image.height,
        "brightness": round(ImageStat.Stat(gray).mean[0], 1),
        "dhash": dhash(gray),
    }
    return out.getvalue(), meta


def _fit(image: Image.Image, width: int) -> Image.Image:
    image = image.convert("RGB")
    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return image


def process_frames(raws: list[bytes], width: int, quality: int) -> tuple[bytes, dict[str, Any]]:
    """Median of a short clip as one JPEG, plus QC stats and clip motion.

    One frame behaves like `process_frame` (motion unknown).
    """
    if len(raws) == 1:
        jpeg, meta = process_frame(raws[0], width, quality)
        return jpeg, {**meta, "n_frames": 1, "motion": None}
    frames = [_fit(Image.open(io.BytesIO(raw)), width) for raw in raws]
    size = frames[0].size
    frames = [f if f.size == size else f.resize(size) for f in frames]
    stack = np.stack([np.asarray(f, dtype=np.uint8) for f in frames])
    median = Image.fromarray(np.median(stack, axis=0).round().astype(np.uint8), "RGB")
    grays = np.stack([np.asarray(f.convert("L"), dtype=np.float32) for f in frames])
    motion = float(np.abs(np.diff(grays, axis=0)).mean())
    jpeg, meta = process_frame(_encode(median), width, quality)
    return jpeg, {**meta, "n_frames": len(frames), "motion": round(motion, 3)}


def _encode(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def ffmpeg_frames(
    url: str, referer: str | None, count: int = 8, fps: float = 2, timeout_s: float = 45
) -> list[bytes]:
    """Decode `count` frames at `fps` from the live edge of an HLS stream."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not installed")
    headers = f"User-Agent: {user_agent()}\r\n"
    if referer:
        headers += f"Referer: {referer}\r\n"
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            exe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-headers",
            headers,
            "-i",
            url,
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(count),
            "-q:v",
            "2",
            str(Path(tmp) / "f%02d.jpg"),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
        frames = [p.read_bytes() for p in sorted(Path(tmp).glob("f*.jpg"))]
    if proc.returncode != 0 or not frames:
        stderr = proc.stderr.decode(errors="replace").strip()[-300:]
        raise RuntimeError(f"ffmpeg exit {proc.returncode}: {stderr}")
    return frames


def browser_probe(page_url: str, timeout_s: float = 60) -> tuple[list[str], bytes | None]:
    """Load the page headlessly; return stream URLs it requested and a video screenshot.

    Raises ImportError when the optional `browser` extra isn't installed.
    """
    from playwright.sync_api import sync_playwright  # pyright: ignore[reportMissingImports]

    streams: list[str] = []
    screenshot: bytes | None = None
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"],
        )
        try:
            page = browser.new_page(
                viewport={"width": 1280, "height": 800}, user_agent=user_agent()
            )
            page.on("request", lambda r: streams.append(r.url) if ".m3u8" in r.url else None)
            page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            for _ in range(20):  # up to ~20 s for the player to request its stream
                if streams:
                    break
                page.wait_for_timeout(1000)
            if not streams:
                for frame in page.frames:
                    video = frame.query_selector("video")
                    if video:
                        page.wait_for_timeout(3000)
                        screenshot = video.screenshot(type="jpeg", quality=90)
                        break
        finally:
            browser.close()
    return unique(streams), screenshot


def _try_hls(
    candidates: list[str], referer: str | None, attempts: list[str], count: int
) -> tuple[list[bytes] | None, str | None]:
    for url in candidates:
        try:
            return ffmpeg_frames(url, referer, count=count), url
        except Exception as exc:
            attempts.append(f"hls {url[:80]}: {describe_error(exc)}")
    return None, None


def _last_hash(ctx: FetchContext) -> str | None:
    recent = [
        r
        for r in ctx.previous
        if r.status == "ok" and r.meta.get("dhash") and ctx.now - r.run_at <= FROZEN_WINDOW
    ]
    return str(max(recent, key=lambda r: r.run_at).meta["dhash"]) if recent else None


def capture(ctx: FetchContext) -> list[Item]:
    width = int(ctx.params.get("width", 960))
    quality = int(ctx.params.get("jpeg_quality", 75))
    count = int(ctx.params.get("clip_frames", 8))
    page_url: str | None = ctx.params.get("page_url")
    attempts: list[str] = []
    raws: list[bytes] | None = None
    source_url: str | None = None
    strategy: str | None = None

    snapshot_url = ctx.params.get("snapshot_url")
    if snapshot_url:
        try:
            raws = [get_with_retry(ctx.client, snapshot_url, sleep=ctx.sleep).content]
            source_url, strategy = snapshot_url, "snapshot"
        except Exception as exc:
            attempts.append(f"snapshot: {describe_error(exc)}")

    if raws is None:
        candidates: list[str] = [ctx.params["hls_url"]] if ctx.params.get("hls_url") else []
        if not candidates and page_url:
            try:
                page = get_with_retry(ctx.client, page_url, sleep=ctx.sleep)
                candidates = find_m3u8(page.text)
            except Exception as exc:
                attempts.append(f"page: {describe_error(exc)}")
        raws, source_url = _try_hls(candidates, page_url, attempts, count)
        strategy = "hls" if raws else None

    if raws is None and page_url:
        try:
            streams, screenshot = browser_probe(page_url)
            raws, source_url = _try_hls(streams, page_url, attempts, count)
            if raws is not None:
                strategy = "browser-hls"
            elif screenshot is not None:
                raws, source_url, strategy = [screenshot], page_url, "browser-screenshot"
            else:
                attempts.append("browser: no stream request or <video> found")
        except ImportError:
            attempts.append("browser: playwright not installed")
        except Exception as exc:
            attempts.append(f"browser: {describe_error(exc)}")

    if raws is None:
        return [ItemError(error="; ".join(attempts) or "no capture strategy", url=page_url)]

    try:
        jpeg, meta = process_frames(raws, width, quality)
    except Exception as exc:
        return [ItemError(error=f"not an image: {describe_error(exc)}", url=source_url)]

    previous_hash = _last_hash(ctx)
    same = previous_hash is not None and hamming(previous_hash, meta["dhash"]) <= FROZEN_MAX_BITS
    motion = meta.get("motion")
    meta.update(
        strategy=strategy,
        sun_elevation=round(sun_elevation(ctx.location.lat, ctx.location.lon, ctx.now), 1),
        same_as_previous=same,
        # A clip that doesn't move is a stuck stream. A single still can only be
        # compared with the last one, which murky, featureless water also matches.
        frozen=motion < FROZEN_MOTION if motion is not None else same,
    )
    return [RawSnapshot(content=jpeg, ext="jpg", url=source_url or "", meta=meta)]
