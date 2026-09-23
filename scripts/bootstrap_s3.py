"""Idempotent S3 bootstrap for the assistant audio store.

Creates the audio bucket and its 90-day expiration lifecycle rule if missing.
Run against the deployment's S3 (or a localstack/moto-equivalent for tests):

    python scripts/bootstrap_s3.py

Configuration via environment:
    S3_ENDPOINT_URL  (default http://127.0.0.1:9000 — local staging)
    S3_BUCKET        (default assistant-audio)
    S3_ACCESS_KEY / S3_SECRET_KEY (defaults are local-staging placeholders)
    S3_LIFECYCLE_DAYS (default 90)
"""

import os

import boto3
from botocore.config import Config

ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
BUCKET = os.getenv("S3_BUCKET", "assistant-audio")
LIFECYCLE_DAYS = int(os.getenv("S3_LIFECYCLE_DAYS", "90"))


def main() -> None:
    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "evoa-local"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", "evoa-local-secret"),
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )

    try:
        s3.head_bucket(Bucket=BUCKET)
        print(f"bucket '{BUCKET}' already exists")
    except Exception:
        s3.create_bucket(Bucket=BUCKET)
        print(f"created bucket '{BUCKET}'")

    # Audio is disposable: TTS output is regenerated on demand, so the whole
    # bucket expires after the retention window.
    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-audio",
                    "Status": "Enabled",
                    "Prefix": "",
                    "Expiration": {"Days": LIFECYCLE_DAYS},
                }
            ]
        },
    )
    cfg = s3.get_bucket_lifecycle_configuration(Bucket=BUCKET)
    rule = cfg["Rules"][0]
    print(
        f"lifecycle rule '{rule['ID']}' active: "
        f"expiration after {rule['Expiration']['Days']} days"
    )


if __name__ == "__main__":
    main()
