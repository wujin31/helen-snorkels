"""One shared HTTP client with timeouts, an identifying User-Agent and retries."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from snorkel import __version__

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_CONTACT = "https://github.com/wujin31/helen-snorkels"


def user_agent() -> str:
    # NWS asks every client to identify itself with a way to reach the owner.
    contact = os.environ.get("SNORKEL_CONTACT") or DEFAULT_CONTACT
    return f"snorkel-status/{__version__} ({contact})"


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": user_agent()},
        follow_redirects=True,
        transport=transport,
    )


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    content: bytes | None = None,
    attempts: int = 3,
    backoff_s: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """Send with exponential backoff on transport errors, 429 and 5xx.

    Other 4xx responses raise immediately: retrying a bad request is impolite.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.request(method, url, params=params, headers=headers, content=content)
        except httpx.TransportError as exc:
            last = exc
        else:
            if response.status_code not in RETRY_STATUS:
                response.raise_for_status()
                return response
            last = httpx.HTTPStatusError(
                f"HTTP {response.status_code} from {url}",
                request=response.request,
                response=response,
            )
        if attempt < attempts - 1:
            sleep(backoff_s * 2**attempt)
    assert last is not None
    raise last


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    attempts: int = 3,
    backoff_s: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    return request_with_retry(
        client,
        "GET",
        url,
        params=params,
        headers=headers,
        attempts=attempts,
        backoff_s=backoff_s,
        sleep=sleep,
    )
