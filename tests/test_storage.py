from pathlib import Path

import httpx
import pytest

from snorkel.storage import GatewayStorage, GitHubOidcToken, LocalStorage, storage_from_spec


def test_local_roundtrip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    assert storage.get("a/b.txt") is None
    storage.put("a/b.txt", b"hi", "text/plain")
    assert storage.get("a/b.txt") == b"hi"


def test_local_delete(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    storage.put("frames/x.jpg", b"\xff", "image/jpeg")
    assert storage.delete("frames/x.jpg") is True
    assert storage.get("frames/x.jpg") is None
    assert storage.delete("frames/x.jpg") is False


def test_local_rejects_escaping_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).put("../evil", b"x", "text/plain")


def test_spec_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(storage_from_spec(f"local:{tmp_path}"), LocalStorage)
    for name in ("S3_ENDPOINT", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="S3_ENDPOINT"):
        storage_from_spec("s3")
    with pytest.raises(ValueError, match="unknown storage"):
        storage_from_spec("ftp://nope")


def test_s3_spec_builds_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ENDPOINT", "https://example.supabase.co/storage/v1/s3")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret")
    storage = storage_from_spec("s3:archive")
    assert storage.describe().startswith("s3:archive")


GATEWAY = "https://ref.supabase.co/functions/v1/archive-gateway"


def gateway_client(objects: dict[str, bytes], seen: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["authorization"] == "Bearer tok"
        key = request.url.path.split("/object/", 1)[1]
        if request.method == "PUT":
            objects[key] = request.content
            return httpx.Response(200, json={"key": key})
        if request.method == "DELETE":
            if objects.pop(key, None) is None:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json={"key": key, "deleted": True})
        if key in objects:
            return httpx.Response(200, content=objects[key])
        return httpx.Response(404, json={"error": "not found"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gateway_roundtrip() -> None:
    objects: dict[str, bytes] = {}
    seen: list[httpx.Request] = []
    storage = GatewayStorage(GATEWAY, lambda: "tok", client=gateway_client(objects, seen))
    assert storage.get("manifest/2026-09-27/archive.jsonl") is None
    storage.put("frames/cam/2026/09/27/160000Z.jpg", b"\xff\xd8", "image/jpeg")
    assert storage.get("frames/cam/2026/09/27/160000Z.jpg") == b"\xff\xd8"
    put = next(r for r in seen if r.method == "PUT")
    assert put.headers["content-type"] == "image/jpeg"
    assert str(put.url) == f"{GATEWAY}/object/frames/cam/2026/09/27/160000Z.jpg"


def test_gateway_raises_on_auth_failure() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    storage = GatewayStorage(GATEWAY, lambda: "tok", client=client, sleep=lambda _s: None)
    with pytest.raises(httpx.HTTPStatusError):
        storage.get("raw/x")


def test_oidc_token_is_requested_with_audience_and_cached() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"value": f"jwt{len(calls)}"})

    now = [0.0]
    token = GitHubOidcToken(
        environ={
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://gh.test/token?api-version=2.0",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "req",
        },
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: now[0],
    )
    assert token() == "jwt1"
    assert token() == "jwt1"
    now[0] = 300
    assert token() == "jwt2"
    assert calls[0].url.params["audience"] == "snorkel-status"
    assert calls[0].url.params["api-version"] == "2.0"
    assert calls[0].headers["authorization"] == "bearer req"


def test_oidc_token_needs_actions_context() -> None:
    with pytest.raises(ValueError, match="OIDC"):
        GitHubOidcToken(environ={})


def test_check_storage_command(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from snorkel.cli import app

    result = CliRunner().invoke(app, ["check-storage", "--storage", f"local:{tmp_path}"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "state/healthcheck/latest.txt").read_bytes().startswith(b"ok ")


def test_gateway_delete() -> None:
    objects = {"frames/a.jpg": b"\xff"}
    seen: list[httpx.Request] = []
    storage = GatewayStorage(GATEWAY, lambda: "tok", client=gateway_client(objects, seen))
    assert storage.delete("frames/a.jpg") is True
    assert storage.delete("frames/a.jpg") is False
    assert objects == {}
