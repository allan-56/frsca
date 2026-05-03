import argparse
import os
import json

def get_features(entity_rows: str, feature_refs: str) -> str:
    """
    Mock Feast feature retrieval.
    In a real app, this would use the Feast SDK to fetch online features.
    """
    print(f"Fetching features {feature_refs} for entities {entity_rows}")

    # Mock data return (Iris-like)
    data = {
        "features": [
            [5.1, 3.5, 1.4, 0.2],
            [4.9, 3.0, 1.4, 0.2],
            [4.7, 3.2, 1.3, 0.2]
        ],
        "labels": [0, 0, 0]
    }
    return json.dumps(data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity-rows", required=True)
    parser.add_argument("--feature-refs", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    features = get_features(args.entity_rows, args.feature_refs)

    with open(args.output_path, "w") as f:
        f.write(features)
