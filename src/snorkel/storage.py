"""Object storage for the archive: frames, raw snapshots and manifests.

Three backends behind one small interface:

- `LocalStorage` writes under a directory (dev and tests).
- `GatewayStorage` (production) goes through the `archive-gateway` Supabase
  edge function, authenticated with GitHub Actions' short-lived OIDC token,
  so no storage secret is stored anywhere.
- `S3Storage` talks to any S3-compatible store (Supabase's S3 endpoint or
  Cloudflare R2) if we ever outgrow the gateway.

Nothing written here ever goes into git.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from snorkel.http import request_with_retry


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def delete(self, key: str) -> bool:
        """Remove an object; True if it existed."""
        ...

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

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.exists():
            return False
        path.unlink()
        return True

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

    def delete(self, key: str) -> bool:
        existed = self.get(key) is not None
        self._client.delete_object(Bucket=self.bucket, Key=key)
        return existed

    def describe(self) -> str:
        return f"s3:{self.bucket} @ {self.endpoint_url}"


OIDC_AUDIENCE = "snorkel-status"


class GitHubOidcToken:
    """Mints GitHub Actions OIDC tokens (needs `permissions: id-token: write`).

    Tokens live about five minutes, so one is reused for four and then renewed.
    """

    def __init__(
        self,
        audience: str = OIDC_AUDIENCE,
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        environ = environ if environ is not None else os.environ
        self._request_url = environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
        self._request_token = environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
        if not self._request_url or not self._request_token:
            raise ValueError(
                "no GitHub Actions OIDC context; run inside Actions with id-token: write"
            )
        self.audience = audience
        self._client = client or httpx.Client(timeout=30)
        self._clock = clock
        self._token: str | None = None
        self._minted_at = 0.0

    def __call__(self) -> str:
        if self._token is None or self._clock() - self._minted_at > 240:
            sep = "&" if "?" in self._request_url else "?"
            response = request_with_retry(
                self._client,
                "GET",
                f"{self._request_url}{sep}audience={quote(self.audience)}",
                headers={"Authorization": f"bearer {self._request_token}"},
            )
            self._token = str(response.json()["value"])
            self._minted_at = self._clock()
        return self._token


class GatewayStorage:
    def __init__(
        self,
        base_url: str,
        token: Callable[[], str],
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._client = client or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
        self._sleep = sleep

    def _url(self, key: str) -> str:
        return f"{self.base_url}/object/{quote(key, safe='/')}"

    def put(self, key: str, data: bytes, content_type: str) -> None:
        request_with_retry(
            self._client,
            "PUT",
            self._url(key),
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": content_type},
            content=data,
            sleep=self._sleep,
        )

    def get(self, key: str) -> bytes | None:
        try:
            response = request_with_retry(
                self._client,
                "GET",
                self._url(key),
                headers={"Authorization": f"Bearer {self._token()}"},
                sleep=self._sleep,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return response.content

    def delete(self, key: str) -> bool:
        try:
            request_with_retry(
                self._client,
                "DELETE",
                self._url(key),
                headers={"Authorization": f"Bearer {self._token()}"},
                sleep=self._sleep,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise
        return True

    def describe(self) -> str:
        return f"gateway:{self.base_url}"


def storage_from_spec(spec: str | None = None) -> Storage:
    """Build storage from `local:<dir>`, `gateway:<url>` or `s3[:<bucket>]`.

    Defaults to $SNORKEL_STORAGE, then `local:.archive`. The gateway
    authenticates with GitHub Actions OIDC. S3 credentials come from
    S3_ENDPOINT, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY and (unless
    given in the spec) S3_BUCKET.
    """
    spec = spec or os.environ.get("SNORKEL_STORAGE") or "local:.archive"
    if spec.startswith("local:"):
        return LocalStorage(Path(spec.removeprefix("local:")))
    if spec.startswith("gateway:"):
        return GatewayStorage(spec.removeprefix("gateway:"), GitHubOidcToken())
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
    raise ValueError(
        f"unknown storage spec {spec!r}; use local:<dir>, gateway:<url> or s3[:<bucket>]"
    )
