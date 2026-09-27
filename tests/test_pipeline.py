from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from snorkel.config import load_sources, load_spots
from snorkel.fetch import cdip as cdip_fetch
from snorkel.pipeline import gather
from snorkel.score.config import load_scoring
from snorkel.score.run import score_all

NOW = datetime(2026, 9, 27, 15, 0, tzinfo=UTC)


def test_everything_down_still_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> bytes:
        raise OSError("NetCDF: I/O failure")

    monkeypatch.setattr(cdip_fetch, "dataset_subset_bytes", refuse)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="gone")

    spots, sources = load_spots(), load_sources()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cond = gather(client, NOW, spots, sources)
    doc = score_all(cond, spots, sources, load_scoring())

    assert {s.verdict for s in doc.spots} == {"unknown"}
    assert doc.summary == "Not enough fresh data to call it right now."
    assert doc.best_bet is None
    assert doc.sources and all(h.stale for h in doc.sources)
    assert all(h.error for h in doc.sources if not h.ok)
    # The document must serialize: the page renders from it no matter what.
    assert '"verdict":"unknown"' in doc.model_dump_json()
