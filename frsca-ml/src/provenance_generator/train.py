import argparse
import json
import os
import sys
import time
from .utils import calculate_sha256, write_tekton_result

def run_train(dataset_url: str, feature_view_id: str, hyperparameters: str, output_dir: str):
    print(f"Starting Training with {dataset_url}, features={feature_view_id}, hp={hyperparameters}")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Simulate Training
    time.sleep(1) # Fake work
    model_path = os.path.join(output_dir, "model.pt")
    with open(model_path, "wb") as f:
        f.write(f"MODEL_CONTENT-{feature_view_id}".encode())

    model_digest = calculate_sha256(model_path)

    # 2. Generate Metrics
    metrics = {"accuracy": 0.88, "loss": 0.15}

    # 3. Generate Attestation
    predicate = {
        "predicateType": "https://frsca.dev/provenance/ml-training/v0.2",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://frsca.dev/ml/build/v1",
                "externalParameters": {
                    "featureViewId": feature_view_id,
                    "datasetUrl": dataset_url,
                    "hyperparameters": json.loads(hyperparameters)
                }
            },
            "runDetails": {
                "builder": {"id": "frsca-training-task"},
                "metadata": {
                    "startedOn": "2023-10-27T10:15:00Z",
                    "finishedOn": "2023-10-27T10:30:00Z"
                }
            },
            "mlSpecifics": {
                "hyperparameters": json.loads(hyperparameters),
                "environment": {
                    "framework": "pytorch",
                    "frameworkVersion": "2.0.1",
                    "accelerator": "cpu"
                },
                "metrics": metrics,
                "datasets": [
                    {
                        "name": "training-data",
                        "uri": dataset_url,
                        "digest": {"sha256": "fake-digest"}
                    }
                ],
                "featureViews": [
                    {
                        "id": feature_view_id,
                        "uri": f"s3://features/{feature_view_id}"
                    }
                ]
            }
        }
    }

    # Save outputs
    with open(os.path.join(output_dir, "training_attestation.json"), "w") as f:
        json.dump(predicate, f, indent=2)

    print(f"Training complete. Model Digest: {model_digest}")

    # Write Tekton Results
    write_tekton_result("MODEL_DIGEST", model_digest)
    write_tekton_result("TRAINING_METRICS", json.dumps(metrics))
    write_tekton_result("ATTESTATION_URI", os.path.join(output_dir, "training_attestation.json"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-url", required=True)
    parser.add_argument("--feature-view-id", required=True)
    parser.add_argument("--hyperparameters", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run_train(args.dataset_url, args.feature_view_id, args.hyperparameters, args.output_dir)
