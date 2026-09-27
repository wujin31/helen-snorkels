"""Shared pieces for fetchers.

A source's capture function takes a `FetchContext` and returns a list of
items, each either a `RawSnapshot` (bytes to archive as-is) or an `ItemError`.
One failing item never stops the others, and one failing source never stops
the archiver (see `snorkel.archive`).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

import httpx

from snorkel.http import get_with_retry
from snorkel.models import CaptureRecord, Location, SpotConfig

T = TypeVar("T")


@dataclass
class RawSnapshot:
    content: bytes
    ext: str
    url: str
    variant: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ItemError:
    error: str
    url: str | None = None
    variant: str | None = None


Item = RawSnapshot | ItemError


class SkipSource(Exception):  # noqa: N818 - it's a signal, not a failure
    """Raised when a source can't run yet, e.g. a station ID isn't configured."""


@dataclass
class FetchContext:
    client: httpx.Client
    now: datetime
    spots: list[SpotConfig]
    params: dict[str, Any]
    location: Location
    previous: list[CaptureRecord] = field(default_factory=list)
    sleep: Callable[[float], None] = time.sleep

    def require(self, key: str) -> Any:
        value = self.params.get(key)
        if value in (None, "", [], {}):
            raise SkipSource(f"{key} not configured")
        return value


SourceFn = Callable[[FetchContext], list[Item]]


@dataclass
class HttpItem:
    url: str
    ext: str
    variant: str | None = None
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    check: Callable[[bytes], None] | None = None
    """Raise to flag a logical error in a 200 response (e.g. CO-OPS error JSON)."""
    transform: Callable[[bytes], bytes] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def describe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


def get_many(ctx: FetchContext, items: Iterable[HttpItem]) -> list[Item]:
    out: list[Item] = []
    for item in items:
        try:
            response = get_with_retry(
                ctx.client, item.url, params=item.params, headers=item.headers, sleep=ctx.sleep
            )
            body = response.content
            if item.check:
                item.check(body)
            if item.transform:
                body = item.transform(body)
            out.append(
                RawSnapshot(
                    content=body,
                    ext=item.ext,
                    url=str(response.url),
                    variant=item.variant,
                    meta=dict(item.meta),
                )
            )
        except Exception as exc:
            out.append(ItemError(error=describe_error(exc), url=item.url, variant=item.variant))
    return out


def unique(values: Iterable[T]) -> list[T]:
    seen: set[T] = set()
    out: list[T] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:80]
