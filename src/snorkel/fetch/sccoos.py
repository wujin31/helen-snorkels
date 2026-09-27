"""SCCOOS Scripps Pier shore station (ERDDAP) and the weekly HAB page."""

from __future__ import annotations

from snorkel.fetch.base import FetchContext, HttpItem, Item, get_many


def pier_url(erddap: str, dataset: str, hours: float) -> str:
    # ERDDAP's relative-time constraint; '>' must be percent-encoded.
    return f"{erddap.rstrip('/')}/tabledap/{dataset}.csv?&time%3E=now-{hours:g}hours"


def capture_pier(ctx: FetchContext) -> list[Item]:
    dataset = str(ctx.require("dataset"))
    url = pier_url(str(ctx.require("erddap")), dataset, float(ctx.params.get("hours", 2)))
    return get_many(ctx, [HttpItem(url=url, ext="csv", variant=dataset)])


def capture_habs(ctx: FetchContext) -> list[Item]:
    return get_many(ctx, [HttpItem(url=str(ctx.require("url")), ext="html")])
