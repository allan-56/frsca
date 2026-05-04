#!/usr/bin/env python3
"""
End-to-end validation test for FRSCA-ML.

Demonstrates:
1. SafeTensor artifact validation (binary hash + header verification)
2. SPDX 3.0.1 AI profile document generation
3. Full provenance chain: training -> artifact hash -> SPDX SBOM

Usage:
  python frsca-ml/tests/test_artifact_and_spdx.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from provenance_generator.artifact_validator import (
    compute_file_hash,
    detect_artifact_type,
    validate_artifact,
    validate_safetensors_header,
)
from provenance_generator.spdx_ai import (
    create_ai_package,
    create_dataset_package,
    create_spdx_document,
    create_training_build,
    generate_spdx_from_provenance,
)


def create_mock_safetensors(path: str, tensors: dict = None):
    """Create a minimal valid safetensors file for testing."""
    import struct

    if tensors is None:
        tensors = {
            "embedding.weight": {"dtype": "F32", "shape": [100, 64], "data_offsets": [0, 25600]},
            "classifier.weight": {"dtype": "F32", "shape": [2, 100], "data_offsets": [25600, 26400]},
            "classifier.bias": {"dtype": "F32", "shape": [2], "data_offsets": [26400, 26408]},
        }

    header = json.dumps(tensors).encode("utf-8")
    header_size = struct.pack("<Q", len(header))

    total_data = 0
    for info in tensors.values():
        if "data_offsets" in info and len(info["data_offsets"]) == 2:
            total_data = max(total_data, info["data_offsets"][1])

    with open(path, "wb") as f:
        f.write(header_size)
        f.write(header)
        f.write(b"\x00" * total_data)


def test_artifact_validation():
    print("=== Test 1: SafeTensor Artifact Validation ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        st_path = os.path.join(tmpdir, "model.safetensors")
        create_mock_safetensors(st_path)

        print(f"Created mock safetensors file: {st_path}")
        print(f"  Size: {os.path.getsize(st_path)} bytes")

        artifact_type = detect_artifact_type(st_path)
        print(f"  Detected type: {artifact_type}")
        assert artifact_type == "application/vnd.safetensors", f"Expected safetensors, got {artifact_type}"

        file_hash = compute_file_hash(st_path)
        print(f"  SHA256: {file_hash}")
        assert len(file_hash) == 64, "SHA256 should be 64 hex chars"

        header_result = validate_safetensors_header(st_path)
        print(f"  Header valid: {header_result['valid']}")
        print(f"  Tensor count: {header_result['tensor_count']}")
        print(f"  Tensor names: {header_result['tensor_names']}")
        assert header_result["valid"], f"Header validation failed: {header_result['error']}"
        assert header_result["tensor_count"] == 3

        validation = validate_artifact(st_path)
        print(f"  Full validation: {validation['valid']}")
        print(f"  Artifact type: {validation['artifact_type']}")
        assert validation["valid"]
        assert validation["sha256"] == file_hash

        print("\n  [PASS] SafeTensor artifact validation works correctly.\n")

    return file_hash


def test_spdx_generation():
    print("=== Test 2: SPDX 3.0.1 AI Profile Generation ===\n")

    ai_pkg = create_ai_package(
        name="distilbert-finetuned-imdb",
        version="1.0.0",
        download_location="https://huggingface.co/example/distilbert-imdb/model.safetensors",
        sha256="a]1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        model_type="transformer",
        domain=["nlp", "sentiment-analysis"],
        hyperparameters={"epochs": 3, "batch_size": 8, "learning_rate": 5e-5},
        metrics={"eval_accuracy": 0.92, "eval_loss": 0.21},
        training_info="Fine-tuned on IMDB dataset using Hugging Face Transformers",
        safety_risk="low",
        standard_compliance=["EU AI Act", "NIST AI RMF"],
    )
    print(f"  Created AIPackage: {ai_pkg['name']}")
    print(f"  Type: {ai_pkg['typeOfModel']}")
    print(f"  Metrics: {[e['key'] + '=' + str(e['value']) for e in ai_pkg['metric']]}")
    print(f"  Compliance: {ai_pkg['standardCompliance']}")

    ds_pkg = create_dataset_package(
        name="imdb",
        version="1.0",
        download_location="https://huggingface.co/datasets/imdb",
        sha256="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
        dataset_type="text",
        has_sensitive_pii=False,
        data_preprocessing="tokenization with distilbert tokenizer",
    )
    print(f"  Created DatasetPackage: {ds_pkg['name']}")

    build = create_training_build(
        build_id="frsca-hf-finetune-task",
        builder_id="frsca-hf-finetune-task",
        start_time="2026-05-04T10:00:00Z",
        end_time="2026-05-04T10:15:00Z",
        source_uri="hf://imdb",
        source_digest="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
        parameters={"epochs": 3, "batch_size": 8},
    )
    print(f"  Created Build: {build['buildId']}")

    doc = create_spdx_document(
        document_name="distilbert-imdb-sbom",
        ai_packages=[ai_pkg],
        dataset_packages=[ds_pkg],
        builds=[build],
    )
    print(f"\n  SPDX Document: {doc['name']}")
    print(f"  Profile conformance: {doc['profileConformance']}")
    print(f"  Elements: {len(doc['element'])}")
    print(f"  Relationships: {len(doc['relationship'])}")

    print("\n  Relationship graph:")
    for rel in doc["relationship"]:
        print(f"    {rel['from']} --[{rel['relationshipType']}]--> {rel['to'][:40]}...")

    print("\n  [PASS] SPDX AI profile document generated successfully.\n")
    return doc


def test_spdx_from_provenance():
    print("=== Test 3: SPDX from Provenance Attestation ===\n")

    mock_provenance = {
        "predicateType": "https://frsca.dev/provenance/ml-training/v0.2",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://frsca.dev/ml/build/v1",
                "externalParameters": {
                    "model": "distilbert-base-uncased",
                    "dataset": "imdb",
                    "epochs": 3,
                },
            },
            "runDetails": {
                "builder": {"id": "frsca-hf-finetune-task"},
                "metadata": {
                    "startedOn": "2026-05-04T10:00:00Z",
                    "finishedOn": "2026-05-04T10:15:00Z",
                },
            },
            "mlSpecifics": {
                "hyperparameters": {"epochs": 3, "batch_size": 8, "lr": 5e-5},
                "environment": {
                    "framework": "pytorch",
                    "frameworkVersion": "2.4.0",
                    "modelFormat": "safetensors",
                },
                "metrics": {"accuracy": 0.92, "loss": 0.21},
            },
        },
    }

    doc = generate_spdx_from_provenance(
        provenance=mock_provenance,
        model_name="distilbert-finetuned-imdb",
        model_version="1.0.0",
        model_download_url="https://huggingface.co/example/model.safetensors",
        model_sha256="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        dataset_name="imdb",
        dataset_url="hf://imdb",
        dataset_sha256="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
    )

    print(f"  Document: {doc['name']}")
    print(f"  Elements: {len(doc['element'])}")
    for elem in doc["element"]:
        elem_type = elem.get("type", "unknown")
        elem_name = elem.get("name", elem.get("buildId", "unknown"))
        print(f"    - [{elem_type}] {elem_name}")

    print(f"\n  Relationships: {len(doc['relationship'])}")
    for rel in doc["relationship"]:
        print(f"    {rel['from']} --[{rel['relationshipType']}]--> {rel['to'][:50]}")

    print("\n  [PASS] SPDX generated from provenance attestation.\n")
    return doc


def test_full_chain():
    print("=== Test 4: Full Provenance Chain ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        st_path = os.path.join(tmpdir, "model.safetensors")
        create_mock_safetensors(st_path)

        validation = validate_artifact(st_path)
        print(f"  Artifact validated: {validation['valid']}")
        print(f"  SHA256: {validation['sha256']}")

        doc = generate_spdx_from_provenance(
            provenance={
                "predicate": {
                    "buildDefinition": {"buildType": "https://frsca.dev/ml/build/v1"},
                    "runDetails": {
                        "builder": {"id": "frsca-hf-finetune-task"},
                        "metadata": {"startedOn": "2026-05-04T10:00:00Z", "finishedOn": "2026-05-04T10:15:00Z"},
                    },
                    "mlSpecifics": {
                        "hyperparameters": {"epochs": 1},
                        "environment": {"framework": "pytorch", "frameworkVersion": "2.4.0"},
                        "metrics": {"accuracy": 0.88},
                    },
                }
            },
            model_name="test-model",
            model_version="0.1",
            model_download_url=f"file://{st_path}",
            model_sha256=validation["sha256"],
        )

        for elem in doc["element"]:
            if elem.get("type") == "AIPackage":
                hashes = elem.get("verifiedUsing", [])
                for h in hashes:
                    print(f"  SPDX verifiedUsing: {h['algorithm']}={h['hashValue'][:32]}...")
                    assert h["hashValue"] == validation["sha256"], "Hash mismatch!"
                    print("  Hash matches artifact!")

        out_path = os.path.join(tmpdir, "sbom.spdx.json")
        with open(out_path, "w") as f:
            json.dump(doc, f, indent=2)
        print(f"\n  SPDX document written to: {out_path}")
        print(f"  Size: {os.path.getsize(out_path)} bytes")

        print("\n  [PASS] Full chain: safetensors -> hash -> SPDX verifiedUsing.\n")


if __name__ == "__main__":
    print("=" * 60)
    print("FRSCA-ML Artifact Validation & SPDX AI Profile Tests")
    print("=" * 60)
    print()

    test_artifact_validation()
    test_spdx_generation()
    test_spdx_from_provenance()
    test_full_chain()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
