"""Object storage: the S3 signature, the filesystem backend and the configuration rules."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from eurogas_nexus.runtime_store.object_store import (
    EMPTY_SHA256,
    FilesystemObjectStore,
    ObjectStoreError,
    ObjectStoreNotConfigured,
    S3ObjectStore,
    object_store_from_environment,
    sign_v4,
)


def test_signature_matches_the_published_aws_example() -> None:
    """AWS's own worked example (GET Object with a Range header, Signature Version 4)."""

    headers = sign_v4(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        path="/test.txt",
        query={},
        headers={"Range": "bytes=0-9"},
        payload_sha256=EMPTY_SHA256,
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        now=datetime(2013, 5, 24, tzinfo=UTC),
    )
    assert headers["authorization"].endswith(
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )
    assert "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in headers["authorization"]
    assert headers["x-amz-date"] == "20130524T000000Z"


def test_filesystem_store_round_trip_and_verify(tmp_path) -> None:
    store = FilesystemObjectStore(tmp_path / "bucket")
    stored = store.put_bytes("archive/2026/a.jsonl.gz", b"payload")
    assert stored.size == 7
    assert store.get_bytes("archive/2026/a.jsonl.gz") == b"payload"
    assert store.size("archive/2026/a.jsonl.gz") == 7
    assert store.size("archive/missing") is None
    assert store.verify("archive/2026/a.jsonl.gz", sha256=stored.sha256, size=7)
    assert not store.verify("archive/2026/a.jsonl.gz", sha256=EMPTY_SHA256, size=7)

    source = tmp_path / "file.bin"
    source.write_bytes(os.urandom(2048))
    on_store = store.put_file("files/file.bin", source)
    copy = tmp_path / "copy.bin"
    assert store.get_to_file("files/file.bin", copy).sha256 == on_store.sha256
    assert copy.read_bytes() == source.read_bytes()
    with pytest.raises(ObjectStoreError):
        store.get_bytes("files/none.bin")


@pytest.mark.parametrize("key", ["", "/", "a/../b", "a//b", "./a"])
def test_keys_cannot_escape_the_store(tmp_path, key) -> None:
    with pytest.raises(ValueError):
        FilesystemObjectStore(tmp_path).put_bytes(key, b"x")


def test_configuration_from_environment(tmp_path) -> None:
    with pytest.raises(ObjectStoreNotConfigured):
        object_store_from_environment({})
    store = object_store_from_environment(
        {"EUROGAS_NEXUS_OBJECT_STORE_URL": f"file://{tmp_path}"}
    )
    assert isinstance(store, FilesystemObjectStore)

    s3 = object_store_from_environment(
        {
            "EUROGAS_NEXUS_OBJECT_STORE_URL": "s3://nexus-archive/site-a",
            "EUROGAS_NEXUS_OBJECT_STORE_ENDPOINT": "https://objects.example.internal:9000",
            "EUROGAS_NEXUS_OBJECT_STORE_ACCESS_KEY_ID": "key-id",
            "EUROGAS_NEXUS_OBJECT_STORE_SECRET_ACCESS_KEY": "never-printed",
        }
    )
    assert isinstance(s3, S3ObjectStore)
    assert s3.uri_style == "path"
    assert s3.describe() == "s3://nexus-archive/site-a at https://objects.example.internal:9000"
    assert "never-printed" not in s3.describe()

    aws = object_store_from_environment(
        {
            "EUROGAS_NEXUS_OBJECT_STORE_URL": "s3://nexus-archive",
            "EUROGAS_NEXUS_OBJECT_STORE_REGION": "eu-central-1",
            "AWS_ACCESS_KEY_ID": "key-id",
            "AWS_SECRET_ACCESS_KEY": "secret",
        }
    )
    assert aws.uri_style == "host"
    assert aws.describe().endswith("https://s3.eu-central-1.amazonaws.com")

    with pytest.raises(ObjectStoreNotConfigured):
        object_store_from_environment({"EUROGAS_NEXUS_OBJECT_STORE_URL": "s3://bucket"})
    with pytest.raises(ValueError):
        object_store_from_environment({"EUROGAS_NEXUS_OBJECT_STORE_URL": "ftp://bucket"})


@pytest.mark.skipif(
    not os.environ.get("EUROGAS_NEXUS_TEST_OBJECT_STORE_URL"),
    reason="set EUROGAS_NEXUS_TEST_OBJECT_STORE_* to run against a real S3-compatible store",
)
def test_round_trip_against_a_real_s3_compatible_store(tmp_path) -> None:
    """Run by the drills' test double (SeaweedFS, Apache-2.0) or any S3-compatible store."""

    prefix = "EUROGAS_NEXUS_TEST_OBJECT_STORE_"
    environment = {
        name.replace(prefix, "EUROGAS_NEXUS_OBJECT_STORE_"): value
        for name, value in os.environ.items()
        if name.startswith(prefix)
    }
    store = object_store_from_environment(environment)
    store.ensure_bucket()
    stored = store.put_bytes("tests/round trip+1.txt", b"hello")
    assert store.get_bytes("tests/round trip+1.txt") == b"hello"
    assert store.verify("tests/round trip+1.txt", sha256=stored.sha256, size=5)
    assert store.size("tests/does-not-exist") is None
