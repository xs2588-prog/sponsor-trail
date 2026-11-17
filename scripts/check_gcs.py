"""List expected GCS files without downloading them: uv run python -m scripts.check_gcs."""
import argparse
from google.cloud import storage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uri', default='gs://sponsortrail_01/clean_dataset')
    args = parser.parse_args()
    if not args.uri.startswith('gs://'):
        parser.error('--uri must start with gs://')
    bucket, _, prefix = args.uri[5:].partition('/')
    prefix = prefix.strip('/')
    prefix = prefix + '/' if prefix else ''
    client = storage.Client(project='sponsor-trail-514122')
    found = set()
    for blob in client.list_blobs(bucket, prefix=prefix):
        if blob.name.endswith('.parquet'):
            print(f'gs://{bucket}/{blob.name}  {blob.size:,} bytes  generation={blob.generation}')
            if blob.name[len(prefix):] in {'lca.parquet', 'uscis.parquet', 'perm.parquet'}:
                found.add(blob.name[len(prefix):])
    missing = {'lca.parquet', 'uscis.parquet', 'perm.parquet'} - found
    if missing:
        raise SystemExit(f'Missing directly under {args.uri}: {sorted(missing)}. Set --uri to their common folder.')
    print('All three sources present. No files downloaded.')


if __name__ == '__main__':
    main()
