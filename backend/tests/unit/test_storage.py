import os
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from botocore.exceptions import ClientError

from app.core.storage import LocalFileStorageBackend, R2FileStorageBackend


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


@pytest.fixture
def r2_backend():
    # boto3.client(...) never makes a network call at construction time, so
    # this is safe with fake credentials — the mock swap below is what
    # actually prevents any real R2/network call from happening in put/get/
    # delete_object.
    backend = R2FileStorageBackend(
        bucket="test-bucket",
        endpoint_url="https://example.r2.cloudflarestorage.com",
        access_key_id="fake-key",
        secret_access_key="fake-secret",
        region="auto",
    )
    backend._client = MagicMock()
    return backend


class TestR2FileStorageBackend:
    async def test_save_calls_put_object_with_bucket_key_and_body(self, r2_backend: R2FileStorageBackend) -> None:
        await r2_backend.save(key="tenant-a/PATIENT_DOCUMENT/owner-1/file.pdf", content=b"hello world")
        r2_backend._client.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="tenant-a/PATIENT_DOCUMENT/owner-1/file.pdf", Body=b"hello world"
        )

    async def test_read_returns_the_streamed_body_bytes(self, r2_backend: R2FileStorageBackend) -> None:
        body = MagicMock()
        body.read.return_value = b"hello world"
        r2_backend._client.get_object.return_value = {"Body": body}

        result = await r2_backend.read(key="file.pdf")

        assert result == b"hello world"
        r2_backend._client.get_object.assert_called_once_with(Bucket="test-bucket", Key="file.pdf")

    async def test_read_missing_key_raises_file_not_found(self, r2_backend: R2FileStorageBackend) -> None:
        r2_backend._client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        with pytest.raises(FileNotFoundError):
            await r2_backend.read(key="does/not/exist.pdf")

    async def test_read_non_not_found_client_error_propagates_unchanged(self, r2_backend: R2FileStorageBackend) -> None:
        r2_backend._client.get_object.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "x"}}, "GetObject")
        with pytest.raises(ClientError):
            await r2_backend.read(key="forbidden.pdf")

    async def test_delete_calls_delete_object_and_is_idempotent_by_design(self, r2_backend: R2FileStorageBackend) -> None:
        await r2_backend.delete(key="file.pdf")
        r2_backend._client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="file.pdf")
