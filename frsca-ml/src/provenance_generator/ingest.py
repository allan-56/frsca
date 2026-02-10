import argparse
import json
import os
import sys
from .utils import calculate_sha256, download_s3_file, write_tekton_result

def validate_schema(filepath: str) -> bool:
    """Mock schema validation."""
    print(f"Validating schema for {filepath}...")
    return True

def check_pii(filepath: str) -> bool:
    """Mock PII check."""
    print(f"Checking for PII in {filepath}...")
    return False # No PII found

def run_ingest(dataset_url: str, output_dir: str):
    print(f"Starting Data Ingestion for {dataset_url}")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Fetch Dataset
    dataset_path = None
    if dataset_url.startswith("s3://"):
        try:
            dataset_path = download_s3_file(dataset_url, output_dir)
        except Exception as e:
            print(f"Error downloading dataset: {e}")
            sys.exit(1)
    else:
        # Mock download for local file
        dataset_path = os.path.join(output_dir, "dataset.csv")
        with open(dataset_path, "w") as f:
            f.write("col1,col2\n1,2\n3,4") # Mock data

    if not dataset_path:
        print("Failed to acquire dataset.")
        sys.exit(1)

    # 2. Validation & PII Check
    if not validate_schema(dataset_path):
        print("Schema validation failed.")
        sys.exit(1)

    if check_pii(dataset_path):
        print("PII detected! Aborting.")
        sys.exit(1)

    # 3. Generate Snapshot ID / Digest
    digest = calculate_sha256(dataset_path)
    snapshot_id = f"snap-{digest[:8]}"

    # 4. Generate Attestation (Predicate)
    predicate = {
        "predicateType": "https://frsca.dev/provenance/dataset/v1",
        "predicate": {
            "dataset": {
                "name": os.path.basename(dataset_path),
                "uri": dataset_url,
                "digest": {"sha256": digest}
            },
            "verification": {
                "verifiedOn": "2023-10-27T10:00:00Z", # Mock timestamp
                "verifier": {"id": "frsca-ingest-task"}
            }
        }
    }

    # Save outputs
    with open(os.path.join(output_dir, "ingest_attestation.json"), "w") as f:
        json.dump(predicate, f, indent=2)

    print(f"Ingestion complete. Snapshot ID: {snapshot_id}")

    # Write Tekton Results
    write_tekton_result("DATA_SNAPSHOT_ID", snapshot_id)
    write_tekton_result("DATA_DIGEST", digest)
    write_tekton_result("ATTESTATION_URI", os.path.join(output_dir, "ingest_attestation.json"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-url", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run_ingest(args.dataset_url, args.output_dir)
