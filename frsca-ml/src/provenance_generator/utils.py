import hashlib
import os
import json
import boto3
from urllib.parse import urlparse

def calculate_sha256(filepath: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def download_s3_file(url: str, dest_dir: str) -> str:
    """Downloads a file from S3 if valid, else returns None."""
    parsed = urlparse(url)
    if parsed.scheme != "s3":
        return None

    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    filename = os.path.basename(key) or "downloaded.file"
    dest_path = os.path.join(dest_dir, filename)

    print(f"Downloading s3://{bucket}/{key} to {dest_path}...")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", None)
    s3 = boto3.client("s3", endpoint_url=endpoint_url)
    s3.download_file(bucket, key, dest_path)
    return dest_path

def write_tekton_result(key: str, value: str):
    """Writes a key-value pair to /tekton/results/KEY."""
    results_dir = "/tekton/results"
    if os.path.exists(results_dir):
        path = os.path.join(results_dir, key)
        with open(path, "w") as f:
            f.write(value)
    else:
        print(f"[Mock Tekton] {key} = {value}")
