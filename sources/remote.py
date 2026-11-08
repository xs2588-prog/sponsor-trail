"""Download the cleaned parquet files from GCS when the server starts.

Cloud Run: set SPONSOR_GCS_URI=gs://<bucket>/clean and give the service account
Storage Object Viewer on the bucket. Locally: leave it unset and keep the files in data/clean/.
"""

import logging
import os
from pathlib import Path

from sources.base import DATA_DIR

log = logging.getLogger(__name__)


def sync_from_gcs(uri: str | None = None, dest: str | Path = DATA_DIR, client=None) -> list[str]:
    """Copy every .parquet under gs://bucket/prefix into dest. Skips files already there with the same size."""
    uri = uri or os.environ.get("SPONSOR_GCS_URI")
    if not uri:
        return []
    if not uri.startswith("gs://"):
        raise ValueError(f"SPONSOR_GCS_URI must look like gs://bucket/folder, got {uri!r}")
    bucket_name, _, prefix = uri[len("gs://"):].partition("/")
    if client is None:
        from google.cloud import storage  # installed with google-cloud-aiplatform
        client = storage.Client()

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        if not blob.name.endswith(".parquet"):
            continue
        target = dest / Path(blob.name).name
        if target.exists() and target.stat().st_size == blob.size:
            continue
        log.info("downloading gs://%s/%s -> %s", bucket_name, blob.name, target)
        blob.download_to_filename(str(target))
        downloaded.append(target.name)
    return downloaded
