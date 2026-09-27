import httpx
import pytest

from snorkel.http import get_with_retry, user_agent

from .conftest import make_client


def test_retries_5xx_then_succeeds() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, text="ok")

    sleeps: list[float] = []
    response = get_with_retry(make_client(handler), "https://x.test/a", sleep=sleeps.append)
    assert response.text == "ok"
    assert len(calls) == 3
    assert sleeps == [2.0, 4.0]


def test_does_not_retry_4xx() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(make_client(handler), "https://x.test/a", sleep=lambda _s: None)
    assert len(calls) == 1


def test_gives_up_after_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(httpx.ConnectError):
        get_with_retry(make_client(handler), "https://x.test/a", sleep=lambda _s: None)


def test_user_agent_identifies_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SNORKEL_CONTACT", raising=False)
    assert "snorkel-status/" in user_agent()
    monkeypatch.setenv("SNORKEL_CONTACT", "someone@example.com")
    assert "someone@example.com" in user_agent()
