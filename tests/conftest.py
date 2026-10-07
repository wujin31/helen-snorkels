from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from snorkel.config import load_sources, load_spots
from snorkel.fetch.base import FetchContext
from snorkel.models import SourcesConfig, SpotConfig

Handler = Callable[[httpx.Request], httpx.Response]

# 2026-09-27 09:00 PDT: well after sunrise in La Jolla.
MORNING = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)


@pytest.fixture
def spots() -> list[SpotConfig]:
    return load_spots()


@pytest.fixture
def sources() -> SourcesConfig:
    return load_sources()


def make_client(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def make_ctx(
    handler: Handler,
    spots: list[SpotConfig],
    sources: SourcesConfig,
    source_id: str,
    now: datetime = MORNING,
    **param_overrides: object,
) -> FetchContext:
    params = dict(sources.sources[source_id])
    params.update(param_overrides)
    return FetchContext(
        client=make_client(handler),
        now=now,
        spots=spots,
        params=params,
        location=sources.location,
        sleep=lambda _s: None,
    )
