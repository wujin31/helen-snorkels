from __future__ import annotations

import io
from datetime import timedelta

import httpx
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

    grabbed: list[tuple[str, str | None]] = []

    def fake_ffmpeg(url: str, referer: str | None, timeout_s: float = 45) -> bytes:
        grabbed.append((url, referer))
        return jpeg()

    monkeypatch.setattr(cam, "ffmpeg_frame", fake_ffmpeg)
    ctx = make_ctx(handler, spots, sources, "cam.scripps_pier")
    [item] = cam.capture(ctx)
    assert isinstance(item, RawSnapshot)
    assert item.meta["strategy"] == "hls"
    assert grabbed == [(stream, sources.sources["cam.scripps_pier"]["page_url"])]


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
    assert item.meta["frozen"] is True


def test_non_image_is_an_error(spots: list[SpotConfig], sources: SourcesConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login</html>")

    ctx = make_ctx(handler, spots, sources, "cam.scripps_pier", snapshot_url="https://still.test/a")
    [item] = cam.capture(ctx)
    assert isinstance(item, ItemError)
    assert "not an image" in item.error
