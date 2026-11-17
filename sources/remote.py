"""Download the cleaned parquet files from GCS when the server starts.

Cloud Run: set SPONSOR_GCS_URI=gs://<bucket>/clean and give the service account
Storage Object Viewer on the bucket. Locally: leave it unset and keep the files in data/clean/.
"""

import logging
import os
import tempfile
from pathlib import Path

from sources.base import DATA_DIR

log = logging.getLogger(__name__)


def sync_from_gcs(uri: str | None = None, dest: str | Path = DATA_DIR, client=None) -> list[str]:
    """Atomically sync the three source files directly under a GCS prefix, using object generations."""
    uri = uri or os.environ.get("SPONSOR_GCS_URI")
    if not uri:
        return []
    if not uri.startswith("gs://"):
        raise ValueError(f"SPONSOR_GCS_URI must look like gs://bucket/folder, got {uri!r}")
    bucket_name, _, prefix = uri[len("gs://"):].partition("/")
    if not bucket_name:
        raise ValueError("SPONSOR_GCS_URI must include a bucket name")
    prefix = prefix.strip("/")
    prefix = prefix + "/" if prefix else ""
    if client is None:
        from google.cloud import storage  # installed with google-cloud-aiplatform
        client = storage.Client()

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        relative = blob.name[len(prefix):] if blob.name.startswith(prefix) else ""
        if relative not in {"lca.parquet", "uscis.parquet", "perm.parquet"}:
            continue
        target = dest / relative
        version = str(getattr(blob, "generation", None) or "")
        marker = target.with_suffix(".generation")
        unchanged = (not version or (marker.exists() and marker.read_text() == version))
        if target.exists() and target.stat().st_size == blob.size and unchanged:
            continue
        log.info("downloading gs://%s/%s -> %s", bucket_name, blob.name, target)
        # A failed download must not leave a partial file that looks ready on the next startup.
        fd, temporary = tempfile.mkstemp(dir=dest, suffix=".partial")
        os.close(fd)
        try:
            blob.download_to_filename(temporary)
            if Path(temporary).stat().st_size != blob.size:
                raise ValueError(f"Incomplete download for {blob.name}")
            os.replace(temporary, target)
            marker.write_text(version)
        finally:
            Path(temporary).unlink(missing_ok=True)
        downloaded.append(target.name)
    return downloaded
