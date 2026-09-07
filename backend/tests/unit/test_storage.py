import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest

from app.core.storage import LocalFileStorageBackend


@pytest.fixture
def backend(tmp_path):
    return LocalFileStorageBackend(tmp_path)


class TestLocalFileStorageBackend:
    async def test_save_then_read_round_trips(self, backend: LocalFileStorageBackend) -> None:
        await backend.save(key="tenant-a/PATIENT_DOCUMENT/owner-1/file.pdf", content=b"hello world")
        assert await backend.read(key="tenant-a/PATIENT_DOCUMENT/owner-1/file.pdf") == b"hello world"

    async def test_save_creates_intermediate_directories(self, backend: LocalFileStorageBackend, tmp_path) -> None:
        await backend.save(key="a/b/c/d.txt", content=b"nested")
        assert (tmp_path / "a" / "b" / "c" / "d.txt").read_bytes() == b"nested"

    async def test_read_missing_key_raises_file_not_found(self, backend: LocalFileStorageBackend) -> None:
        with pytest.raises(FileNotFoundError):
            await backend.read(key="does/not/exist.txt")

    async def test_delete_is_idempotent_for_a_missing_key(self, backend: LocalFileStorageBackend) -> None:
        await backend.delete(key="never-existed.txt")  # must not raise

    async def test_delete_removes_the_file(self, backend: LocalFileStorageBackend, tmp_path) -> None:
        await backend.save(key="file.txt", content=b"x")
        await backend.delete(key="file.txt")
        assert not (tmp_path / "file.txt").exists()

    async def test_overwriting_an_existing_key_replaces_content(self, backend: LocalFileStorageBackend) -> None:
        await backend.save(key="file.txt", content=b"first")
        await backend.save(key="file.txt", content=b"second")
        assert await backend.read(key="file.txt") == b"second"

    async def test_path_traversal_in_key_is_rejected(self, backend: LocalFileStorageBackend) -> None:
        with pytest.raises(ValueError):
            await backend.save(key="../../etc/passwd", content=b"x")
