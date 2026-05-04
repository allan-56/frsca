"""
Integration tests: SPDX AI profile generation from real artifacts.

Tests the full chain:
  Real artifact → hash → provenance → SPDX document → validate structure
"""

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from provenance_generator.spdx_ai import (
    create_ai_package,
    create_dataset_package,
    create_spdx_document,
    create_training_build,
    generate_spdx_from_provenance,
)


class TestSPDXFromRealArtifacts:
    """Generate SPDX documents from actual artifact files."""

    def test_spdx_with_safetensors_hash(self, tmp_artifacts):
        """SPDX document contains correct hash of real safetensors file."""
        art = tmp_artifacts["safetensors"]

        pkg = create_ai_package(
            name="test-model",
            version="1.0",
            download_location=f"file://{art['path']}",
            sha256=art["sha256"],
            model_type="transformer",
            metrics={"accuracy": 0.92},
        )

        hashes = pkg["verifiedUsing"]
        assert len(hashes) == 1
        assert hashes[0]["algorithm"] == "sha256"
        assert hashes[0]["hashValue"] == art["sha256"]

    def test_spdx_full_document_structure(self, tmp_artifacts):
        """Full SPDX document has all required elements and relationships."""
        art = tmp_artifacts["safetensors"]

        ai_pkg = create_ai_package(
            name="test-model",
            version="1.0",
            download_location=f"file://{art['path']}",
            sha256=art["sha256"],
            model_type="pytorch",
            domain=["nlp"],
            hyperparameters={"lr": 0.001, "epochs": 5},
            metrics={"accuracy": 0.95},
            training_info="Fine-tuned on custom dataset",
            safety_risk="low",
            standard_compliance=["EU AI Act"],
        )

        ds_pkg = create_dataset_package(
            name="custom-dataset",
            version="1.0",
            download_location="s3://data/train.parquet",
            sha256="a" * 64,
            dataset_type="text",
            has_sensitive_pii=False,
        )

        build = create_training_build(
            build_id="test-run-001",
            builder_id="integration-test",
            start_time="2026-05-04T10:00:00Z",
            end_time="2026-05-04T10:15:00Z",
            source_uri="s3://data/train.parquet",
            source_digest="a" * 64,
            parameters={"lr": 0.001},
        )

        doc = create_spdx_document(
            document_name="test-sbom",
            ai_packages=[ai_pkg],
            dataset_packages=[ds_pkg],
            builds=[build],
        )

        assert doc["type"] == "SpdxDocument"
        assert doc["name"] == "test-sbom"
        assert "ai" in doc["profileConformance"]
        assert "dataset" in doc["profileConformance"]
        assert "build" in doc["profileConformance"]

        element_types = {e["type"] for e in doc["element"]}
        assert "AIPackage" in element_types
        assert "DatasetPackage" in element_types
        assert "Build" in element_types

        rel_types = {r["relationshipType"] for r in doc["relationship"]}
        assert "verifiedUsing" in rel_types
        assert "trainedOn" in rel_types
        assert "builtBy" in rel_types

    def test_spdx_from_provenance_attestation(self, tmp_artifacts):
        """Generate SPDX from an in-toto provenance attestation."""
        art = tmp_artifacts["safetensors"]

        provenance = {
            "predicate": {
                "buildDefinition": {
                    "buildType": "https://frsca.dev/ml/build/v1",
                    "externalParameters": {"dataset": "imdb"},
                },
                "runDetails": {
                    "builder": {"id": "test-builder"},
                    "metadata": {
                        "startedOn": "2026-05-04T10:00:00Z",
                        "finishedOn": "2026-05-04T10:15:00Z",
                    },
                },
                "mlSpecifics": {
                    "hyperparameters": {"epochs": 3},
                    "environment": {
                        "framework": "pytorch",
                        "frameworkVersion": "2.4.0",
                    },
                    "metrics": {"accuracy": 0.91, "loss": 0.09},
                },
            }
        }

        doc = generate_spdx_from_provenance(
            provenance=provenance,
            model_name="test-model",
            model_version="1.0",
            model_download_url=f"file://{art['path']}",
            model_sha256=art["sha256"],
            dataset_name="imdb",
            dataset_url="hf://imdb",
            dataset_sha256="b" * 64,
        )

        ai_pkg = [e for e in doc["element"] if e["type"] == "AIPackage"][0]
        assert ai_pkg["verifiedUsing"][0]["hashValue"] == art["sha256"]
        assert ai_pkg["metric"][0]["key"] == "accuracy"
        assert ai_pkg["metric"][0]["value"] == "0.91"

        ds_pkgs = [e for e in doc["element"] if e["type"] == "DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "imdb"

    def test_spdx_json_serialization(self, tmp_artifacts, tmp_path):
        """SPDX document serializes to valid JSON."""
        art = tmp_artifacts["safetensors"]

        doc = create_spdx_document(
            document_name="serialization-test",
            ai_packages=[
                create_ai_package(
                    name="test-model",
                    version="1.0",
                    download_location=f"file://{art['path']}",
                    sha256=art["sha256"],
                )
            ],
        )

        out_path = str(tmp_path / "test.spdx.json")
        with open(out_path, "w") as f:
            json.dump(doc, f, indent=2)

        with open(out_path) as f:
            loaded = json.load(f)

        assert loaded["type"] == "SpdxDocument"
        assert loaded["element"][0]["verifiedUsing"][0]["hashValue"] == art["sha256"]

    def test_spdx_hash_consistency(self, tmp_artifacts):
        """Multiple SPDX generations produce consistent hashes."""
        art = tmp_artifacts["safetensors"]

        docs = []
        for i in range(3):
            doc = generate_spdx_from_provenance(
                provenance={
                    "predicate": {
                        "buildDefinition": {"buildType": "test"},
                        "runDetails": {
                            "builder": {"id": "test"},
                            "metadata": {"startedOn": "", "finishedOn": ""},
                        },
                        "mlSpecifics": {
                            "hyperparameters": {},
                            "environment": {"framework": "pytorch"},
                            "metrics": {"accuracy": 0.9},
                        },
                    }
                },
                model_name="test-model",
                model_version="1.0",
                model_download_url=f"file://{art['path']}",
                model_sha256=art["sha256"],
            )
            docs.append(doc)

        hashes = []
        for doc in docs:
            ai_pkg = [e for e in doc["element"] if e["type"] == "AIPackage"][0]
            hashes.append(ai_pkg["verifiedUsing"][0]["hashValue"])

        assert len(set(hashes)) == 1, "Hashes should be identical across runs"
        assert hashes[0] == art["sha256"]
