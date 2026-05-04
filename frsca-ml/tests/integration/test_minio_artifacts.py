"""
Integration tests: MinIO artifact upload, hash computation, provenance capture.

These tests spin up a real MinIO container via testcontainers and verify:
1. Artifact upload to MinIO
2. SHA256 hash computation over S3
3. Provenance attestation generation
4. Attestation storage in MinIO
"""

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from provenance_generator.artifact_validator import (
    compute_file_hash,
    detect_artifact_type,
    validate_artifact,
    validate_safetensors_header,
)

try:
    from frsca_ml_provenance.provenance_hook import capture
except ImportError:
    from provenance_generator.provenance_hook import capture


class TestMinIOArtifactUpload:
    """Upload artifacts to MinIO and verify integrity."""

    def test_upload_safetensors(self, minio_client, tmp_artifacts):
        """Upload a safetensors file to MinIO and verify hash."""
        art = tmp_artifacts["safetensors"]

        minio_client.upload_file(art["path"], "models", "model.safetensors")

        head = minio_client.head_object(Bucket="models", Key="model.safetensors")
        assert head["ContentLength"] == art["size"]

    def test_s3_hash_matches_local(self, minio_client, tmp_artifacts):
        """Verify SHA256 computed via S3 matches local hash."""
        art = tmp_artifacts["safetensors"]

        minio_client.upload_file(art["path"], "models", "model.safetensors")

        from provenance_generator.utils import calculate_sha256

        local_hash = art["sha256"]

        h = hashlib.sha256()
        response = minio_client.head_object(Bucket="models", Key="model.safetensors")
        size = response["ContentLength"]
        offset = 0
        chunk_size = 8 * 1024 * 1024
        while offset < size:
            end = min(offset + chunk_size - 1, size - 1)
            resp = minio_client.get_object(
                Bucket="models", Key="model.safetensors", Range=f"bytes={offset}-{end}"
            )
            h.update(resp["Body"].read())
            offset = end + 1

        s3_hash = h.hexdigest()
        assert s3_hash == local_hash, f"S3 hash {s3_hash} != local hash {local_hash}"

    def test_multiple_artifacts(self, minio_client, tmp_artifacts):
        """Upload multiple artifact types and verify each."""
        for name, art in tmp_artifacts.items():
            ext = os.path.splitext(art["path"])[1]
            key = f"model{ext}"
            minio_client.upload_file(art["path"], "models", key)

            head = minio_client.head_object(Bucket="models", Key=key)
            assert head["ContentLength"] == art["size"], f"Size mismatch for {name}"


class TestSafetensorsValidation:
    """Validate safetensors format parsing."""

    def test_detect_safetensors_type(self, tmp_artifacts):
        """Detect safetensors by magic bytes and extension."""
        art = tmp_artifacts["safetensors"]
        assert detect_artifact_type(art["path"]) == "application/vnd.safetensors"

    def test_detect_bin_type(self, tmp_artifacts):
        """Detect pytorch .bin by extension."""
        art = tmp_artifacts["bin"]
        assert detect_artifact_type(art["path"]) == "application/x-pytorch"

    def test_detect_onnx_type(self, tmp_artifacts):
        """Detect ONNX by extension."""
        art = tmp_artifacts["onnx"]
        assert detect_artifact_type(art["path"]) == "application/onnx"

    def test_safetensors_header_parsing(self, tmp_artifacts):
        """Parse safetensors header and extract tensor info."""
        art = tmp_artifacts["safetensors"]
        result = validate_safetensors_header(art["path"])

        assert result["valid"] is True
        assert result["tensor_count"] == art["tensor_count"]
        assert result["header_size"] > 0
        assert len(result["tensor_names"]) == art["tensor_count"]

    def test_full_artifact_validation(self, tmp_artifacts):
        """Full validation pipeline for safetensors."""
        art = tmp_artifacts["safetensors"]
        result = validate_artifact(art["path"])

        assert result["valid"] is True
        assert result["sha256"] == art["sha256"]
        assert result["artifact_type"] == "application/vnd.safetensors"
        assert result["format_validation"]["valid"] is True

    def test_corrupted_safetensors(self, tmp_path):
        """Detect corrupted safetensors file."""
        bad_path = str(tmp_path / "bad.safetensors")
        with open(bad_path, "wb") as f:
            f.write(b"\x00" * 100)

        result = validate_artifact(bad_path)
        assert result["valid"] is False


class TestProvenanceHookWithMinIO:
    """Test the provenance_hook module against real MinIO."""

    def test_capture_from_local_file(self, tmp_artifacts, tmp_path):
        """Capture provenance from a local file."""
        art = tmp_artifacts["safetensors"]
        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        result = capture(
            model_path=art["path"],
            metrics={"accuracy": 0.95, "loss": 0.05},
            params={"epochs": 10, "lr": 0.001},
            builder_id="test",
            framework="pytorch",
            output_dir=output_dir,
        )

        assert result["artifact"]["digest"] == art["sha256"]
        assert result["artifact"]["media_type"] == "application/vnd.safetensors"
        assert "attestation" in result
        assert "spdx" in result

        att_path = os.path.join(output_dir, "attestation.json")
        spdx_path = os.path.join(output_dir, "sbom.spdx.json")
        assert os.path.exists(att_path)
        assert os.path.exists(spdx_path)

        with open(att_path) as f:
            att = json.load(f)
        assert att["predicateType"] == "https://frsca.dev/provenance/ml-training/v0.2"
        assert att["predicate"]["outputArtifacts"][0]["digest"]["sha256"] == art["sha256"]

        with open(spdx_path) as f:
            spdx = json.load(f)
        assert spdx["type"] == "SpdxDocument"
        assert spdx["profileConformance"] == ["core", "software", "ai", "dataset", "build"]

    def test_capture_from_s3(self, minio_client, minio_endpoint, minio_container, tmp_artifacts, tmp_path):
        """Capture provenance from an S3/MinIO artifact."""
        art = tmp_artifacts["safetensors"]
        minio_client.upload_file(art["path"], "models", "model.safetensors")

        config = minio_container.get_config()
        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        result = capture(
            model_path="s3://models/model.safetensors",
            metrics={"accuracy": 0.92},
            params={"epochs": 5},
            builder_id="test-minio",
            framework="pytorch",
            output_dir=output_dir,
            s3_endpoint_url=minio_endpoint,
            s3_access_key=config["access_key"],
            s3_secret_key=config["secret_key"],
        )

        assert result["artifact"]["digest"] == art["sha256"]
        assert result["artifact"]["size_bytes"] == art["size"]

    def test_provenance_chain_integrity(self, minio_client, minio_endpoint, minio_container, tmp_artifacts, tmp_path):
        """Verify full chain: upload → hash → attest → store."""
        art = tmp_artifacts["safetensors"]
        minio_client.upload_file(art["path"], "models", "model.safetensors")

        config = minio_container.get_config()

        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        result = capture(
            model_path="s3://models/model.safetensors",
            metrics={"accuracy": 0.93},
            params={"batch_size": 32},
            dataset_uri="s3://models/dataset.csv",
            builder_id="integration-test",
            framework="pytorch",
            output_dir=output_dir,
            s3_endpoint_url=minio_endpoint,
            s3_access_key=config["access_key"],
            s3_secret_key=config["secret_key"],
        )

        att = result["attestation"]
        output_art = att["predicate"]["outputArtifacts"][0]
        assert output_art["digest"]["sha256"] == art["sha256"]
        assert output_art["sizeBytes"] == art["size"]
        assert output_art["mediaType"] == "application/vnd.safetensors"

        spdx = result["spdx"]
        ai_pkg = [e for e in spdx["element"] if e["type"] == "AIPackage"][0]
        hash_entry = ai_pkg["verifiedUsing"][0]
        assert hash_entry["hashValue"] == art["sha256"]

        assert att["predicate"]["mlSpecifics"]["datasets"][0]["uri"] == "s3://models/dataset.csv"
