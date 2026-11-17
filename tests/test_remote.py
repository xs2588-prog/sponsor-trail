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
    assert client.calls == [("bucket", "clean/")]
    assert (tmp_path / "lca.parquet").read_bytes() == b"abc"
    assert sync_from_gcs("gs://bucket/clean", tmp_path, client) == []  # same size: skipped


def test_no_uri_means_local_files(monkeypatch, tmp_path):
    monkeypatch.delenv("SPONSOR_GCS_URI", raising=False)
    assert sync_from_gcs(dest=tmp_path) == []


def test_generation_change_redownloads_same_size(tmp_path):
    first = blob('clean/lca.parquet', b'abc')
    first.generation = 1
    sync_from_gcs('gs://bucket/clean', tmp_path, FakeClient([first]))
    second = blob('clean/lca.parquet', b'xyz')
    second.generation = 2
    sync_from_gcs('gs://bucket/clean', tmp_path, FakeClient([second]))
    assert (tmp_path / 'lca.parquet').read_bytes() == b'xyz'


def test_failed_download_preserves_previous_file(tmp_path):
    import pytest
    target = tmp_path / 'lca.parquet'
    target.write_bytes(b'good')
    def fail(path):
        with open(path, 'wb') as stream:
            stream.write(b'bad')
        raise OSError('interrupted')
    broken = SimpleNamespace(name='clean/lca.parquet', size=100, generation=2, download_to_filename=fail)
    with pytest.raises(OSError):
        sync_from_gcs('gs://bucket/clean', tmp_path, FakeClient([broken]))
    assert target.read_bytes() == b'good'
    assert not list(tmp_path.glob('*.partial'))


def test_nested_or_unrelated_files_are_not_flattened(tmp_path):
    files = [blob('clean/nested/lca.parquet', b'abc'), blob('clean/unrelated.parquet', b'x')]
    assert sync_from_gcs('gs://bucket/clean', tmp_path, FakeClient(files)) == []
