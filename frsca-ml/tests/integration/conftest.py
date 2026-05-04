"""
Shared test fixtures for FRSCA-ML integration tests.

Provides:
- MinIO container (via testcontainers)
- Temporary safetensors/artifact files
- S3 client connected to MinIO
- K8s client (if cluster available)
"""

import hashlib
import json
import os
import struct
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def docker_available():
    """Check if Docker is accessible."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def k8s_available():
    """Check if a Kubernetes cluster is accessible."""
    try:
        from kubernetes import client as k8s_client, config
        config.load_incluster_config()
        return True
    except Exception:
        try:
            config.load_kube_config()
            return True
        except Exception:
            return False


def create_mock_safetensors(path: str, num_tensors: int = 3) -> dict:
    """Create a minimal valid safetensors file."""
    tensors = {}
    offset = 0
    for i in range(num_tensors):
        name = f"layer_{i}.weight"
        size = (i + 1) * 1024
        tensors[name] = {
            "dtype": "F32",
            "shape": [size // 4],
            "data_offsets": [offset, offset + size],
        }
        offset += size

    header = json.dumps(tensors).encode("utf-8")
    header_size = struct.pack("<Q", len(header))

    with open(path, "wb") as f:
        f.write(header_size)
        f.write(header)
        f.write(b"\x00" * offset)

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)

    return {
        "path": path,
        "sha256": h.hexdigest(),
        "size": os.path.getsize(path),
        "tensor_count": num_tensors,
        "tensors": tensors,
    }


@pytest.fixture
def tmp_artifacts(tmp_path):
    """Create temporary ML artifacts for testing."""
    artifacts = {}

    st_path = str(tmp_path / "model.safetensors")
    artifacts["safetensors"] = create_mock_safetensors(st_path)

    bin_path = str(tmp_path / "model.bin")
    with open(bin_path, "wb") as f:
        f.write(b"PYTORCH_MAGIC" + os.urandom(1024))
    h = hashlib.sha256()
    with open(bin_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    artifacts["bin"] = {
        "path": bin_path,
        "sha256": h.hexdigest(),
        "size": os.path.getsize(bin_path),
    }

    onnx_path = str(tmp_path / "model.onnx")
    with open(onnx_path, "wb") as f:
        f.write(b"ONNX_MAGIC" + os.urandom(512))
    h = hashlib.sha256()
    with open(onnx_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    artifacts["onnx"] = {
        "path": onnx_path,
        "sha256": h.hexdigest(),
        "size": os.path.getsize(onnx_path),
    }

    return artifacts


@pytest.fixture
def minio_container():
    """Start a MinIO container for integration testing."""
    if not docker_available():
        pytest.skip("Docker not available")

    from testcontainers.minio import MinioContainer

    container = MinioContainer()
    container.start()
    yield container
    container.stop()


@pytest.fixture
def minio_client(minio_container):
    """Get a boto3 S3 client connected to the MinIO container."""
    import boto3

    config = minio_container.get_config()
    endpoint_url = f"http://{config['endpoint']}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
    )

    client.create_bucket(Bucket="models")
    client.create_bucket(Bucket="attestations")

    return client


@pytest.fixture
def minio_endpoint(minio_container):
    """Get the MinIO endpoint URL."""
    config = minio_container.get_config()
    return f"http://{config['endpoint']}"


@pytest.fixture
def k8s_client_instance():
    """Get a Kubernetes client if a cluster is available."""
    if not k8s_available():
        pytest.skip("Kubernetes cluster not available")

    from kubernetes import client as k8s_client, config

    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()

    return k8s_client
