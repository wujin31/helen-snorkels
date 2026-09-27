"""Object storage for the archive: frames, raw snapshots and manifests.

Two backends behind one small interface:

- `LocalStorage` writes under a directory (dev and tests).
- `S3Storage` talks to any S3-compatible store. Production uses Supabase
  Storage's S3 endpoint; Cloudflare R2 would be a change of env vars only.

Nothing written here ever goes into git.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def describe(self) -> str: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"key escapes storage root: {key}")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.exists() else None

    def describe(self) -> str:
        return f"local:{self.root}"


class S3Storage:
    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                s3={"addressing_style": "path"},  # Supabase requires path-style
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=10,
                read_timeout=60,
            ),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise
        return obj["Body"].read()

    def describe(self) -> str:
        return f"s3:{self.bucket} @ {self.endpoint_url}"


def storage_from_spec(spec: str | None = None) -> Storage:
    """Build storage from `local:<dir>` or `s3[:<bucket>]`.

    Defaults to $SNORKEL_STORAGE, then `local:.archive`. S3 credentials come
    from S3_ENDPOINT, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY and
    (unless given in the spec) S3_BUCKET.
    """
    spec = spec or os.environ.get("SNORKEL_STORAGE") or "local:.archive"
    if spec.startswith("local:"):
        return LocalStorage(Path(spec.removeprefix("local:")))
    if spec == "s3" or spec.startswith("s3:"):
        bucket = spec.removeprefix("s3").removeprefix(":") or os.environ.get("S3_BUCKET", "")
        env = {
            name: os.environ.get(name, "")
            for name in ("S3_ENDPOINT", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
        }
        missing = [name for name, value in env.items() if not value]
        if not bucket:
            missing.append("S3_BUCKET")
        if missing:
            raise ValueError(f"S3 storage needs {', '.join(missing)}")
        return S3Storage(
            bucket,
            endpoint_url=env["S3_ENDPOINT"],
            region=os.environ.get("S3_REGION") or "us-east-1",
            access_key_id=env["S3_ACCESS_KEY_ID"],
            secret_access_key=env["S3_SECRET_ACCESS_KEY"],
        )
    raise ValueError(f"unknown storage spec {spec!r}; use local:<dir> or s3[:<bucket>]")
