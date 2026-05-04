"""
FRSCA-ML Provenance Hooks

Drop-in provenance capture for existing ML platforms.
Works with: MLflow, MinIO/S3, Ray/KubeRay, Airflow.

Usage:
  from frsca_ml_provenance import provenance_hook

  # After training completes
  provenance_hook.capture(
      model_path="s3://models/team/model.safetensors",
      mlflow_run_id="abc123",
      metrics={"accuracy": 0.92, "loss": 0.08},
      params={"epochs": 10, "lr": 0.001},
      dataset_uri="s3://data/train.parquet",
  )
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import boto3


def compute_s3_hash(bucket: str, key: str, endpoint_url: Optional[str] = None, access_key: Optional[str] = None, secret_key: Optional[str] = None) -> str:
    """Compute SHA256 of an object in S3/MinIO without downloading the full file."""
    kwargs = {"endpoint_url": endpoint_url} if endpoint_url else {}
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    s3 = boto3.client("s3", **kwargs)
    h = hashlib.sha256()

    response = s3.head_object(Bucket=bucket, Key=key)
    size = response["ContentLength"]

    # Stream in chunks
    offset = 0
    chunk_size = 8 * 1024 * 1024  # 8MB chunks
    while offset < size:
        end = min(offset + chunk_size - 1, size - 1)
        range_header = f"bytes={offset}-{end}"
        resp = s3.get_object(Bucket=bucket, Key=key, Range=range_header)
        h.update(resp["Body"].read())
        offset = end + 1

    return h.hexdigest()


def compute_local_hash(filepath: str) -> str:
    """Compute SHA256 of a local file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_artifact(uri: str, endpoint_url: Optional[str] = None, access_key: Optional[str] = None, secret_key: Optional[str] = None) -> dict:
    """Resolve an artifact URI to its hash, size, and media type."""
    parsed = urlparse(uri)

    if parsed.scheme in ("s3", "s3a"):
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        kwargs = {"endpoint_url": endpoint_url} if endpoint_url else {}
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        s3 = boto3.client("s3", **kwargs)
        head = s3.head_object(Bucket=bucket, Key=key)
        size = head["ContentLength"]
        digest = compute_s3_hash(bucket, key, endpoint_url, access_key, secret_key)
    elif parsed.scheme == "file" or parsed.scheme == "":
        filepath = parsed.path if parsed.scheme == "file" else uri
        size = os.path.getsize(filepath)
        digest = compute_local_hash(filepath)
    else:
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

    ext = os.path.splitext(parsed.path)[1].lower()
    media_types = {
        ".safetensors": "application/vnd.safetensors",
        ".bin": "application/x-pytorch",
        ".pt": "application/x-pytorch",
        ".onnx": "application/onnx",
        ".pkl": "application/x-pickle",
        ".h5": "application/x-hdf5",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return {
        "uri": uri,
        "digest": digest,
        "size_bytes": size,
        "media_type": media_type,
        "filename": os.path.basename(parsed.path),
    }


def capture(
    model_path: str,
    mlflow_run_id: Optional[str] = None,
    metrics: Optional[dict] = None,
    params: Optional[dict] = None,
    dataset_uri: Optional[str] = None,
    dataset_hash: Optional[str] = None,
    builder_id: str = "ml-platform",
    framework: str = "unknown",
    framework_version: str = "unknown",
    output_dir: Optional[str] = None,
    s3_endpoint_url: Optional[str] = None,
    s3_access_key: Optional[str] = None,
    s3_secret_key: Optional[str] = None,
) -> dict:
    """
    Capture provenance for a trained model artifact.

    This function:
    1. Resolves the model artifact (hash, size, type)
    2. Creates an in-toto provenance attestation
    3. Generates an SPDX AI profile document
    4. Writes both to output_dir (or /tekton/results if in a pipeline)

    Args:
        model_path: URI to the model artifact (s3://, file://)
        mlflow_run_id: MLflow run ID (optional)
        metrics: Training metrics dict
        params: Hyperparameters dict
        dataset_uri: URI to the training dataset
        dataset_hash: SHA256 of the dataset (if known)
        builder_id: Identifier for the training system
        framework: ML framework (pytorch, tensorflow, sklearn)
        framework_version: Framework version
        output_dir: Where to write attestation files
        s3_endpoint_url: S3/MinIO endpoint URL

    Returns:
        dict with attestation, spdx, and artifact info
    """
    if metrics is None:
        metrics = {}
    if params is None:
        params = {}

    print(f"[FRSCA-ML] Resolving artifact: {model_path}")
    artifact = resolve_artifact(model_path, s3_endpoint_url, s3_access_key, s3_secret_key)
    print(f"[FRSCA-ML] SHA256: {artifact['digest']}")
    print(f"[FRSCA-ML] Size: {artifact['size_bytes']} bytes")
    print(f"[FRSCA-ML] Type: {artifact['media_type']}")

    now = datetime.now(timezone.utc).isoformat()

    attestation = {
        "predicateType": "https://frsca.dev/provenance/ml-training/v0.2",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://frsca.dev/ml/build/v1",
                "externalParameters": {
                    "modelPath": model_path,
                    "datasetUri": dataset_uri,
                    "hyperparameters": params,
                    "mlflowRunId": mlflow_run_id,
                },
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": {
                    "startedOn": now,
                    "finishedOn": now,
                },
            },
            "mlSpecifics": {
                "hyperparameters": params,
                "environment": {
                    "framework": framework,
                    "frameworkVersion": framework_version,
                    "modelFormat": artifact["media_type"],
                },
                "metrics": metrics,
                "datasets": (
                    [
                        {
                            "name": os.path.basename(urlparse(dataset_uri).path),
                            "uri": dataset_uri,
                            "digest": {"sha256": dataset_hash or "unknown"},
                        }
                    ]
                    if dataset_uri
                    else []
                ),
            },
            "outputArtifacts": [
                {
                    "name": artifact["filename"],
                    "uri": model_path,
                    "digest": {"sha256": artifact["digest"]},
                    "sizeBytes": artifact["size_bytes"],
                    "mediaType": artifact["media_type"],
                }
            ],
        },
    }

    spdx = _generate_spdx(attestation, artifact)

    result = {
        "artifact": artifact,
        "attestation": attestation,
        "spdx": spdx,
    }

    if output_dir is None:
        output_dir = os.environ.get("TEKTON_RESULTS_DIR", "/tekton/results")

    if os.path.exists(output_dir):
        att_path = os.path.join(output_dir, "attestation.json")
        spdx_path = os.path.join(output_dir, "sbom.spdx.json")

        with open(att_path, "w") as f:
            json.dump(attestation, f, indent=2)
        with open(spdx_path, "w") as f:
            json.dump(spdx, f, indent=2)

        print(f"[FRSCA-ML] Attestation written to: {att_path}")
        print(f"[FRSCA-ML] SPDX SBOM written to: {spdx_path}")

        # Write Tekton results if available
        tekton_dir = "/tekton/results"
        if os.path.isdir(tekton_dir):
            for name, value in [
                ("MODEL_DIGEST", artifact["digest"]),
                ("MODEL_PATH", model_path),
                ("TRAINING_METRICS", json.dumps(metrics)),
                ("ATTESTATION_URI", att_path),
            ]:
                with open(os.path.join(tekton_dir, name), "w") as f:
                    f.write(str(value))

    return result


def _generate_spdx(attestation: dict, artifact: dict) -> dict:
    """Generate an SPDX 3.0.1 AI profile document from provenance."""
    pred = attestation["predicate"]
    ml = pred["mlSpecifics"]
    env = ml["environment"]
    build = pred["runDetails"]

    model_name = artifact["filename"].replace(".safetensors", "").replace(".bin", "")

    return {
        "type": "SpdxDocument",
        "spdxId": f"SPDXRef-{model_name}-sbom",
        "name": f"{model_name}-sbom",
        "creationInfo": {
            "type": "CreationInfo",
            "created": datetime.now(timezone.utc).isoformat(),
            "createdBy": ["FRSCA-ML Provenance Hook"],
            "specVersion": "3.0.1",
        },
        "profileConformance": ["core", "software", "ai", "dataset", "build"],
        "element": [
            {
                "type": "AIPackage",
                "spdxId": f"SPDXRef-{model_name}",
                "name": model_name,
                "packageVersion": "1.0.0",
                "downloadLocation": artifact["uri"],
                "primaryPurpose": "model",
                "verifiedUsing": [
                    {
                        "type": "Hash",
                        "algorithm": "sha256",
                        "hashValue": artifact["digest"],
                    }
                ],
                "releaseTime": datetime.now(timezone.utc).isoformat(),
                "typeOfModel": [env.get("framework", "unknown")],
                "domain": ["machine-learning"],
                "hyperparameter": [
                    {"type": "DictionaryEntry", "key": k, "value": str(v)}
                    for k, v in ml.get("hyperparameters", {}).items()
                ],
                "metric": [
                    {"type": "DictionaryEntry", "key": k, "value": str(v)}
                    for k, v in ml.get("metrics", {}).items()
                ],
            }
        ],
        "relationship": [
            {
                "type": "Relationship",
                "spdxId": f"SPDXRef-rel-{model_name}-hash",
                "from": f"SPDXRef-{model_name}",
                "relationshipType": "verifiedUsing",
                "to": artifact["digest"],
            }
        ],
    }


def mlflow_hook(run_id: Optional[str] = None):
    """
    Decorator/context manager that captures provenance after MLflow training.

    Usage:
        import mlflow
        from frsca_ml_provenance import provenance_hook

        with mlflow.start_run() as run:
            # ... train model ...
            mlflow.log_metric("accuracy", 0.92)
            mlflow.log_param("epochs", 10)

            # Capture provenance
            provenance_hook.capture(
                model_path="s3://bucket/model.safetensors",
                mlflow_run_id=run.info.run_id,
                metrics={"accuracy": 0.92},
                params={"epochs": 10},
            )
    """
    pass
