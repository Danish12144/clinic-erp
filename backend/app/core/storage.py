"""File storage abstraction — PRD-ARCHITECTURE.md §15. One interface,
swappable backends: `LocalFileStorageBackend` (dev/self-hosted, writes to
disk) today, an S3/R2-compatible backend later, without any caller
(`app/modules/files/service.py`) needing to change. No S3/R2 credentials
or bucket exist in this environment yet, so only "local" is implemented —
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


def get_storage_backend() -> FileStorageBackend:
    settings = get_settings()
    if settings.file_storage_backend == "local":
        return LocalFileStorageBackend(Path(settings.file_storage_local_dir))
    raise NotImplementedError(
        f"Unsupported file_storage_backend: {settings.file_storage_backend!r} — only 'local' is implemented. "
        "An S3-compatible backend can be added behind this same FileStorageBackend interface without changing any caller."
    )
