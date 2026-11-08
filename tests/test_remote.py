from types import SimpleNamespace

from sources.remote import sync_from_gcs


class FakeClient:
    def __init__(self, blobs):
        self.blobs = blobs
        self.calls = []

    def list_blobs(self, bucket, prefix=""):
        self.calls.append((bucket, prefix))
        return self.blobs


def blob(name, content):
    def download_to_filename(path):
        with open(path, "wb") as f:
            f.write(content)
    return SimpleNamespace(name=name, size=len(content), download_to_filename=download_to_filename)


def test_downloads_parquet_only_and_skips_existing(tmp_path):
    client = FakeClient([blob("clean/lca.parquet", b"abc"), blob("clean/notes.txt", b"x")])
    assert sync_from_gcs("gs://bucket/clean", tmp_path, client) == ["lca.parquet"]
    assert client.calls == [("bucket", "clean")]
    assert (tmp_path / "lca.parquet").read_bytes() == b"abc"
    assert sync_from_gcs("gs://bucket/clean", tmp_path, client) == []  # same size: skipped


def test_no_uri_means_local_files(monkeypatch, tmp_path):
    monkeypatch.delenv("SPONSOR_GCS_URI", raising=False)
    assert sync_from_gcs(dest=tmp_path) == []
