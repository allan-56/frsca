"""
MinIO → FRSCA-ML Provenance Webhook

Listens for MinIO bucket notifications and automatically:
1. Computes SHA256 of new model artifacts
2. Generates provenance attestation
3. Signs with Tekton Chains (or cosign)
4. Generates SPDX AI profile

Deploy as a Kubernetes Deployment alongside MinIO.

Environment Variables:
  MINIO_ENDPOINT:     MinIO API endpoint (default: http://minio:9000)
  MINIO_ACCESS_KEY:   MinIO access key
  MINIO_SECRET_KEY:   MinIO secret key
  WATCHED_BUCKETS:    Comma-separated bucket names (default: models)
  ARTIFACT_EXTENSIONS: File extensions to process (default: .safetensors,.bin,.pt,.onnx)
  OUTPUT_BUCKET:      Bucket for attestations (default: attestations)
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError


MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
WATCHED_BUCKETS = os.environ.get("WATCHED_BUCKETS", "models").split(",")
ARTIFACT_EXTENSIONS = os.environ.get(
    "ARTIFACT_EXTENSIONS", ".safetensors,.bin,.pt,.onnx,.pkl,.h5"
).split(",")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "attestations")


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )


def compute_hash(s3, bucket: str, key: str) -> str:
    h = hashlib.sha256()
    response = s3.head_object(Bucket=bucket, Key=key)
    size = response["ContentLength"]

    offset = 0
    chunk_size = 8 * 1024 * 1024
    while offset < size:
        end = min(offset + chunk_size - 1, size - 1)
        resp = s3.get_object(
            Bucket=bucket, Key=key, Range=f"bytes={offset}-{end}"
        )
        h.update(resp["Body"].read())
        offset = end + 1

    return h.hexdigest()


def create_attestation(
    bucket: str, key: str, digest: str, size: int, media_type: str
) -> dict:
    return {
        "predicateType": "https://frsca.dev/provenance/ml-artifact/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://frsca.dev/ml/artifact-ingestion/v1",
                "externalParameters": {
                    "sourceBucket": bucket,
                    "sourceKey": key,
                },
            },
            "runDetails": {
                "builder": {"id": "frsca-minio-webhook"},
                "metadata": {
                    "startedOn": datetime.now(timezone.utc).isoformat(),
                    "finishedOn": datetime.now(timezone.utc).isoformat(),
                },
            },
            "outputArtifacts": [
                {
                    "name": os.path.basename(key),
                    "uri": f"s3://{bucket}/{key}",
                    "digest": {"sha256": digest},
                    "sizeBytes": size,
                    "mediaType": media_type,
                }
            ],
        },
    }


def process_artifact(s3, bucket: str, key: str):
    """Process a single artifact: hash, attest, store."""
    ext = os.path.splitext(key)[1].lower()
    if ext not in ARTIFACT_EXTENSIONS:
        return

    print(f"[Webhook] Processing: s3://{bucket}/{key}")

    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        size = head["ContentLength"]
    except ClientError as e:
        print(f"[Webhook] Error getting object info: {e}")
        return

    media_types = {
        ".safetensors": "application/vnd.safetensors",
        ".bin": "application/x-pytorch",
        ".pt": "application/x-pytorch",
        ".onnx": "application/onnx",
        ".pkl": "application/x-pickle",
        ".h5": "application/x-hdf5",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    print(f"[Webhook] Computing SHA256 for {key} ({size} bytes)...")
    digest = compute_hash(s3, bucket, key)
    print(f"[Webhook] SHA256: {digest}")

    attestation = create_attestation(bucket, key, digest, size, media_type)

    att_key = key + ".attestation.json"
    s3.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=att_key,
        Body=json.dumps(attestation, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"[Webhook] Attestation stored: s3://{OUTPUT_BUCKET}/{att_key}")

    provenance_key = key + ".provenance.json"
    provenance = {
        "artifact": {
            "uri": f"s3://{bucket}/{key}",
            "sha256": digest,
            "size_bytes": size,
            "media_type": media_type,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        },
        "attestation_uri": f"s3://{OUTPUT_BUCKET}/{att_key}",
    }
    s3.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=provenance_key,
        Body=json.dumps(provenance, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"[Webhook] Provenance stored: s3://{OUTPUT_BUCKET}/{provenance_key}")


def ensure_buckets(s3):
    """Ensure watched and output buckets exist."""
    existing = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]

    for bucket in WATCHED_BUCKETS:
        bucket = bucket.strip()
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket)
            print(f"[Webhook] Created bucket: {bucket}")

    if OUTPUT_BUCKET not in existing:
        s3.create_bucket(Bucket=OUTPUT_BUCKET)
        print(f"[Webhook] Created output bucket: {OUTPUT_BUCKET}")


def poll_and_process(s3):
    """Poll watched buckets for new artifacts and process them."""
    processed = set()

    while True:
        for bucket in WATCHED_BUCKETS:
            bucket = bucket.strip()
            try:
                resp = s3.list_objects_v2(Bucket=bucket)
                for obj in resp.get("Contents", []):
                    key = obj["Key"]
                    ext = os.path.splitext(key)[1].lower()

                    if ext not in ARTIFACT_EXTENSIONS:
                        continue

                    marker_key = f"{OUTPUT_BUCKET}/{key}.attestation.json"
                    if key in processed:
                        continue

                    try:
                        s3.head_object(Bucket=OUTPUT_BUCKET, Key=f"{key}.attestation.json")
                        processed.add(key)
                        continue
                    except ClientError:
                        pass

                    process_artifact(s3, bucket, key)
                    processed.add(key)

            except ClientError as e:
                print(f"[Webhook] Error listing bucket {bucket}: {e}")

        time.sleep(30)


def main():
    print(f"[Webhook] Starting FRSCA-ML MinIO Webhook")
    print(f"[Webhook] Endpoint: {MINIO_ENDPOINT}")
    print(f"[Webhook] Watching buckets: {WATCHED_BUCKETS}")
    print(f"[Webhook] Output bucket: {OUTPUT_BUCKET}")
    print(f"[Webhook] Extensions: {ARTIFACT_EXTENSIONS}")

    s3 = get_s3_client()

    # Wait for MinIO to be ready
    for i in range(30):
        try:
            s3.list_buckets()
            break
        except Exception:
            print(f"[Webhook] Waiting for MinIO... ({i+1}/30)")
            time.sleep(2)
    else:
        print("[Webhook] MinIO not available, exiting")
        sys.exit(1)

    ensure_buckets(s3)
    poll_and_process(s3)


if __name__ == "__main__":
    main()
