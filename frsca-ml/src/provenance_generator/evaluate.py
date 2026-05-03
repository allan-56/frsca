import argparse
import json
import os
import sys
import time
from .utils import calculate_sha256, write_tekton_result

def run_evaluate(model_digest: str, evaluation_data_url: str, output_dir: str):
    print(f"Starting Evaluation for {model_digest} on {evaluation_data_url}")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Simulate Evaluation
    time.sleep(1) # Fake work
    # Generate random metrics > 0.8
    accuracy = 0.92
    loss = 0.08
    metrics = {"accuracy": accuracy, "loss": loss}

    # 2. Generate Attestation
    predicate = {
        "predicateType": "https://frsca.dev/provenance/ml-evaluation/v0.1",
        "predicate": {
            "runDetails": {
                "builder": {"id": "frsca-evaluation-task"},
                "metadata": {
                    "startedOn": "2023-10-27T10:35:00Z",
                    "finishedOn": "2023-10-27T10:40:00Z"
                }
            },
            "evaluationSpecifics": {
                "modelId": "mock-model-v1",
                "modelDigest": {"sha256": model_digest},
                "evaluationDataset": {
                    "name": "eval-data",
                    "uri": evaluation_data_url,
                    "digest": {"sha256": "fake-eval-digest"}
                },
                "metrics": metrics,
                "thresholds": {"accuracy": 0.85},
                "passed": True
            }
        }
    }

    # Save outputs
    with open(os.path.join(output_dir, "evaluation_attestation.json"), "w") as f:
        json.dump(predicate, f, indent=2)

    print(f"Evaluation complete. Metrics: {metrics}")

    # Write Tekton Results
    write_tekton_result("EVALUATION_METRICS", json.dumps(metrics))
    write_tekton_result("PASSED", "true")
    write_tekton_result("ATTESTATION_URI", os.path.join(output_dir, "evaluation_attestation.json"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-digest", required=True)
    parser.add_argument("--evaluation-data-url", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run_evaluate(args.model_digest, args.evaluation_data_url, args.output_dir)
