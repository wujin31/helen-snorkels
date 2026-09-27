"""Beach water-quality advisories and closures.

Until the station endpoints behind sdbeachinfo.com are probed (see
docs/sources.md), this archives the configured pages as-is so the history
exists; parsing comes with the normalized fetchers.
"""

from __future__ import annotations

from snorkel.fetch.base import FetchContext, HttpItem, Item, get_many, slug


def _ext(url: str) -> str:
    return "json" if url.split("?")[0].endswith(".json") else "html"


def capture_pages(ctx: FetchContext) -> list[Item]:
    urls = [str(u) for u in ctx.require("urls")]
    items = [HttpItem(url=u, ext=_ext(u), variant=slug(u.split("://", 1)[-1])) for u in urls]
    return get_many(ctx, items)
