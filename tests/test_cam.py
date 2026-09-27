from __future__ import annotations

import io
from datetime import timedelta

import httpx
import numpy as np
import pytest
from PIL import Image

from snorkel.fetch import cam
from snorkel.fetch.base import ItemError, RawSnapshot
from snorkel.models import CaptureRecord, SourcesConfig, SpotConfig

from .conftest import MORNING, make_ctx


def jpeg(
    width: int = 1920, height: int = 1080, color: tuple[int, int, int] = (40, 120, 160)
) -> bytes:
    image = Image.new("RGB", (width, height), color)
    for x in range(0, width, 97):  # some structure so dHash isn't all zeros
        for y in range(height):
            image.putpixel((x, y), (250, 250, 250))
    out = io.BytesIO()
    image.save(out, "JPEG")
    return out.getvalue()


def test_find_m3u8_handles_escaped_json() -> None:
    page = (
        '<script>var cfg = {"src":"https:\\/\\/edge.example.com\\/live\\/cam.stream'
        '\\/playlist.m3u8?t=abc&amp;x=1"};</script>'
        '<source src="https://edge.example.com/live/cam.stream/playlist.m3u8?t=abc&x=1">'
    )
    assert cam.find_m3u8(page) == [
        "https://edge.example.com/live/cam.stream/playlist.m3u8?t=abc&x=1"
    ]


def test_process_frame_downscales_and_measures() -> None:
    content, meta = cam.process_frame(jpeg(), width=960, quality=75)
    image = Image.open(io.BytesIO(content))
    assert image.size == (960, 540)
    assert meta["width"] == 960 and meta["height"] == 540
    assert 0 < meta["brightness"] < 255
    assert len(meta["dhash"]) == 16


def test_hamming() -> None:
    assert cam.hamming("00000000000000ff", "000000000000000f") == 4


def test_snapshot_strategy(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://still.test/cam.jpg"
        return httpx.Response(200, content=jpeg())

    ctx = make_ctx(
        handler, spots, sources, "cam.scripps_pier", snapshot_url="https://still.test/cam.jpg"
    )
    [item] = cam.capture(ctx)
    assert isinstance(item, RawSnapshot)
    assert item.ext == "jpg"
    assert item.meta["strategy"] == "snapshot"
    assert item.meta["sun_elevation"] > 0
    assert item.meta["frozen"] is False


def test_hls_strategy_from_page(
    spots: list[SpotConfig], sources: SourcesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = "https://edge.test/cam/playlist.m3u8?t=1"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f'<video src="{stream}"></video>')

    grabbed: list[tuple[str, str | None, int]] = []

    def fake_ffmpeg(
        url: str, referer: str | None, count: int = 8, fps: float = 2, timeout_s: float = 45
    ) -> list[bytes]:
        grabbed.append((url, referer, count))
        return [jpeg(color=(40, 120 + i, 160)) for i in range(count)]

    monkeypatch.setattr(cam, "ffmpeg_frames", fake_ffmpeg)
    ctx = make_ctx(handler, spots, sources, "cam.scripps_pier")
    [item] = cam.capture(ctx)
    assert isinstance(item, RawSnapshot)
    assert item.meta["strategy"] == "hls"
    assert item.meta["n_frames"] == 8
    assert item.meta["motion"] > 0 and item.meta["frozen"] is False
    assert grabbed == [(stream, sources.sources["cam.scripps_pier"]["page_url"], 8)]


def test_clip_median_drops_passing_things() -> None:
    base = Image.new("RGB", (320, 180), (30, 90, 110))
    frames = []
    for i in range(5):
        frame = base.copy()
        frame.paste((250, 250, 250), (20 + 60 * i, 60, 60 + 60 * i, 100))  # a fish swims by
        out = io.BytesIO()
        frame.save(out, "PNG")
        frames.append(out.getvalue())
    content, meta = cam.process_frames(frames, width=320, quality=90)
    still = np.asarray(Image.open(io.BytesIO(content)).convert("L"))
    assert max(int(still[80, 40 + 60 * i]) for i in range(5)) < 90  # no fish left
    assert meta["n_frames"] == 5 and meta["motion"] > 1


def test_a_clip_that_does_not_move_is_frozen(
    spots: list[SpotConfig], sources: SourcesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='"https://edge.test/cam/playlist.m3u8"')

    same = jpeg()
    monkeypatch.setattr(cam, "ffmpeg_frames", lambda url, referer, count=8, **_: [same] * count)
    [item] = cam.capture(make_ctx(handler, spots, sources, "cam.scripps_pier"))
    assert isinstance(item, RawSnapshot)
    assert item.meta["motion"] == 0 and item.meta["frozen"] is True


def test_all_strategies_failing_is_one_error(
    spots: list[SpotConfig], sources: SourcesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>no stream here</html>")

    def no_browser(page_url: str, timeout_s: float = 60) -> tuple[list[str], bytes | None]:
        raise ImportError("playwright")

    monkeypatch.setattr(cam, "browser_probe", no_browser)
    [item] = cam.capture(make_ctx(handler, spots, sources, "cam.scripps_pier"))
    assert isinstance(item, ItemError)
    assert "playwright not installed" in item.error


def test_browser_screenshot_fallback(
    spots: list[SpotConfig], sources: SourcesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html></html>")

    monkeypatch.setattr(cam, "browser_probe", lambda page_url, timeout_s=60: ([], jpeg()))
    [item] = cam.capture(make_ctx(handler, spots, sources, "cam.scripps_pier"))
    assert isinstance(item, RawSnapshot)
    assert item.meta["strategy"] == "browser-screenshot"


def test_frozen_stream_is_flagged(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    frame = jpeg()
    _, meta = cam.process_frame(frame, 960, 75)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=frame)

    ctx = make_ctx(handler, spots, sources, "cam.scripps_pier", snapshot_url="https://still.test/a")
    ctx.previous = [
        CaptureRecord(
            source="cam.scripps_pier",
            run_at=MORNING - timedelta(minutes=15),
            status="ok",
            meta={"dhash": meta["dhash"]},
        )
    ]
    [item] = cam.capture(ctx)
    assert isinstance(item, RawSnapshot)
    assert item.meta["frozen"] is True  # one still: only the comparison with the last is possible
    assert item.meta["same_as_previous"] is True


def test_non_image_is_an_error(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login</html>")

    ctx = make_ctx(handler, spots, sources, "cam.scripps_pier", snapshot_url="https://still.test/a")
    [item] = cam.capture(ctx)
    assert isinstance(item, ItemError)
    assert "not an image" in item.error


def test_find_m3u8_decodes_unicode_escapes() -> None:
    page = '"src": "https://live.test/hls/cam.stream/playlist.m3u8?t=abc\\u0026e=123"'
    assert cam.find_m3u8(page) == ["https://live.test/hls/cam.stream/playlist.m3u8?t=abc&e=123"]
