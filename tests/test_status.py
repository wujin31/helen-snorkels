from __future__ import annotations

from snorkel.config import load_spots
from snorkel.models import SourcesConfig
from snorkel.observations import SourceResult, Turbidity
from snorkel.score.config import load_scoring
from snorkel.score.run import empty_conditions, score_all

from .conftest import MORNING


def test_status_links_scripps_cam_page_and_carries_no_cam_data(sources: SourcesConfig) -> None:
    doc = score_all(empty_conditions(MORNING), load_spots(), sources, load_scoring())
    assert doc.cam_url == "https://coollab.ucsd.edu/pierviz/"
    assert '"cam":' not in doc.model_dump_json()


def test_page_hides_an_impossible_turbidity_reading(sources: SourcesConfig) -> None:
    cond = empty_conditions(MORNING)
    cond.turbidity = SourceResult(
        source="sccoos", ok=True, fetched_at=MORNING, value=Turbidity(time=MORNING, ntu=0.07)
    )
    doc = score_all(cond, load_spots(), sources, load_scoring())
    assert doc.day.turbidity_ntu is None
