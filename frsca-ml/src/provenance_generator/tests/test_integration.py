import os
import subprocess
import boto3
import pytest
from testcontainers.minio import MinioContainer

@pytest.fixture(scope="module")
def minio_container():
    # Use Quay to avoid Docker Hub rate limits
    with MinioContainer(image="quay.io/minio/minio:RELEASE.2024-01-31T20-20-33Z") as minio:
        yield minio

def test_provenance_generator_integration(minio_container, tmp_path):
    """
    Integration test using Testcontainers (MinIO).
    1. Uploads a dummy dataset to MinIO.
    2. Runs main.py pointing to that MinIO bucket.
    3. Verifies that main.py downloaded the file and generated artifacts.
    """

    # 1. Setup MinIO Client
    endpoint = minio_container.get_config()["endpoint"]
    access_key = minio_container.get_config()["access_key"]
    secret_key = minio_container.get_config()["secret_key"]

    # MinioContainer might return internal docker IP, we need localhost mapped port usually handled by testcontainers
    # .get_config() returns a dict with 'endpoint', 'access_key', 'secret_key'
    # endpoint is usually host:port

    s3 = boto3.client(
        "s3",
        endpoint_url=f"http://{endpoint}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1"
    )

    bucket_name = "test-bucket"
    s3.create_bucket(Bucket=bucket_name)

    # Upload dummy data
    data_content = b"header1,header2\n1,2\n3,4"
    s3.put_object(Bucket=bucket_name, Key="train.csv", Body=data_content)

    dataset_url = f"s3://{bucket_name}/train.csv"

    # 2. Prepare Environment for Script
    # Pass the endpoint via env var as our script supports it
    env = os.environ.copy()
    env["AWS_ENDPOINT_URL"] = f"http://{endpoint}"
    env["AWS_ACCESS_KEY_ID"] = access_key
    env["AWS_SECRET_ACCESS_KEY"] = secret_key
    env["AWS_DEFAULT_REGION"] = "us-east-1"

    output_dir = tmp_path / "artifacts"

    # 3. Execute main.py
    cmd = [
        "python3", "../main.py",
        "--dataset-url", dataset_url,
        "--hyperparameters", '{"epochs": 1}',
        "--output-dir", str(output_dir)
    ]

    # Running from the tests directory so ../main.py is reachable
    # Adjust CWD to be the directory of this test file
    cwd = os.path.dirname(__file__)

    result = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)

    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    assert result.returncode == 0, "Script failed execution"

    # 4. Verify Artifacts
    model_path = output_dir / "model.pt"
    bom_path = output_dir / "cyclonedx.json"

    assert model_path.exists()
    assert bom_path.exists()

    # Verify content was used
    content = model_path.read_bytes()
    # Our script appends the hash of the dataset to the model file if downloaded
    # Calculate hash of data_content
    import hashlib
    data_hash = hashlib.sha256(data_content).hexdigest()

    assert b"DatasetHash" in content
    assert data_hash.encode() in content

    print("Integration test passed! MinIO interaction successful.")
