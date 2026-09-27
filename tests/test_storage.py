from pathlib import Path

import pytest

from snorkel.storage import LocalStorage, storage_from_spec


def test_local_roundtrip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    assert storage.get("a/b.txt") is None
    storage.put("a/b.txt", b"hi", "text/plain")
    assert storage.get("a/b.txt") == b"hi"


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
