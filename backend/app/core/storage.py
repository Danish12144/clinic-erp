"""File storage abstraction — PRD-ARCHITECTURE.md §15. One interface,
swappable backends: `LocalFileStorageBackend` (dev/self-hosted, writes to
disk) and `R2FileStorageBackend` (Cloudflare R2, production) — no caller
(`app/modules/files/service.py`) needs to change either way.
`get_storage_backend()` raises clearly if a caller asks for anything else,
rather than silently falling back.

`key` is always the caller's responsibility to construct — this module
never invents or validates a key's shape, matching PRD §15's own key
convention (`{tenant_id}/{owner_type}/{owner_id}/{uuid}-{filename}`,
implemented in `app/modules/files/service.py`).
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings


class FileStorageBackend(ABC):
    @abstractmethod
    async def save(self, *, key: str, content: bytes) -> None: ...

    @abstractmethod
    async def read(self, *, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, *, key: str) -> None: ...


class LocalFileStorageBackend(FileStorageBackend):
    """Writes under `base_dir/{key}` — `key` already contains the
    tenant/owner-scoped path, so this backend itself needs no tenant
    awareness. Blocking file I/O is offloaded via `asyncio.to_thread` so it
    doesn't stall the event loop, the same reasoning `MedicineBatchRepository`
    et al. never apply to DB calls (those are already async) but which does
    matter here since `pathlib`/`open` are synchronous."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _resolve(self, key: str) -> Path:
        path = (self._base_dir / key).resolve()
        if self._base_dir.resolve() not in path.parents and path != self._base_dir.resolve():
            # A key containing `../` segments could otherwise escape
            # base_dir — keys are caller-constructed (see module docstring),
            # so this is defense-in-depth, not a response to an expected input.
            raise ValueError(f"Invalid storage key: {key!r}")
        return path

    async def save(self, *, key: str, content: bytes) -> None:
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        await asyncio.to_thread(_write)

    async def read(self, *, key: str) -> bytes:
        path = self._resolve(key)

        def _read() -> bytes:
            return path.read_bytes()

        try:
            return await asyncio.to_thread(_read)
        except FileNotFoundError:
            raise

    async def delete(self, *, key: str) -> None:
        path = self._resolve(key)

        def _delete() -> None:
            path.unlink(missing_ok=True)

        await asyncio.to_thread(_delete)


class R2FileStorageBackend(FileStorageBackend):
    """Cloudflare R2 via boto3's S3-compatible client — R2 implements the
    S3 API, so no R2-specific SDK is needed, only a bucket-scoped
    `endpoint_url` pointing at R2 instead of AWS. `save`/`read`/`delete`
    wrap boto3's synchronous client in `asyncio.to_thread`, the same
    reasoning `LocalFileStorageBackend` uses for blocking `pathlib` I/O —
    boto3 has no native asyncio client, and adding `aioboto3` as a second
    dependency for this wasn't worth it over the one-line wrap.

    `key` needs no path-traversal guard the way `LocalFileStorageBackend`'s
    does — an S3-style object key is a flat namespace string, not a
    filesystem path, so a `../` segment in it is just an unusual key, not
    an escape from anything.

    `read`'s `NoSuchKey` -> `FileNotFoundError` translation exists so
    `FileService.get_document_content`'s `except FileNotFoundError` (built
    against `LocalFileStorageBackend`'s behavior) keeps working unchanged
    regardless of which backend is configured."""

    def __init__(self, *, bucket: str, endpoint_url: str, access_key_id: str, secret_access_key: str, region: str) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            # R2 only supports SigV4, and virtual-hosted-style addressing
            # doesn't work against R2's endpoint shape — path-style is
            # required (confirmed against Cloudflare's own S3-compatibility
            # docs, not assumed).
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    async def save(self, *, key: str, content: bytes) -> None:
        await asyncio.to_thread(self._client.put_object, Bucket=self._bucket, Key=key, Body=content)

    async def read(self, *, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise FileNotFoundError(key) from exc
            raise
        return await asyncio.to_thread(response["Body"].read)

    async def delete(self, *, key: str) -> None:
        # delete_object is idempotent for a missing key (S3-compatible
        # semantics — no error either way), matching
        # LocalFileStorageBackend's own idempotent delete.
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)


def get_storage_backend() -> FileStorageBackend:
    settings = get_settings()
    if settings.file_storage_backend == "local":
        return LocalFileStorageBackend(Path(settings.file_storage_local_dir))
    if settings.file_storage_backend == "r2":
        return R2FileStorageBackend(
            bucket=settings.r2_bucket_name,
            endpoint_url=settings.r2_endpoint_url,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            region=settings.r2_region,
        )
    raise NotImplementedError(
        f"Unsupported file_storage_backend: {settings.file_storage_backend!r} — only 'local' and 'r2' are implemented."
    )
