import argparse
import hashlib
import json
import time
import os
import random
from pathlib import Path
from typing import Dict, Any, List

from pydantic import BaseModel
from cyclonedx.model import XsUri
from cyclonedx.model.bom import Bom, BomMetaData
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.output import OutputFormat
from cyclonedx.output.json import JsonV1Dot6
from packageurl import PackageURL

# Pydantic Models for Input Validation
class Hyperparameters(BaseModel):
    epochs: int = 10
    batch_size: int = 32
    learning_rate: float = 0.001
    optimizer: str = "adam"

class TrainingConfig(BaseModel):
    dataset_url: str
    hyperparameters: Hyperparameters
    output_dir: str

def calculate_sha256(filepath: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def simulate_training() -> Dict[str, float]:
    """Simulates a training run and returns metrics."""
    print("Simulating training...")
    time.sleep(1) # Fake work
    # Generate random metrics > 0.8
    accuracy = 0.8 + (random.random() * 0.19)
    loss = 0.2 - (random.random() * 0.15)
    return {"accuracy": accuracy, "loss": loss}

def create_ai_bom(config: TrainingConfig, metrics: Dict[str, float], model_digest: str) -> Bom:
    bom = Bom()
    bom.metadata = BomMetaData()

    # Create Component for the Model
    # Note: The library might have evolved. I'll use generic structures if specific ML classes aren't fully exposed or if I need to map raw dicts.
    # However, CycloneDX 1.6 support should be in recent versions.
    # We will construct a Component and assume the library handles ModelCard serialization if attached.

    # Since the library version installed (11.6.0) is recent, it should support Model Card.
    # But for safety and strictly following the JSON template requested,
    # I will rely on the library for the BOM envelope and component, but might need to inspect how to attach the model card.

    c = Component(
        name="trained-model",
        version="1.0.0",
        type=ComponentType.MACHINE_LEARNING_MODEL,
        purl=PackageURL(type="generic", name="trained-model", version="1.0.0", qualifiers={"digest": model_digest})
    )

    # IMPORTANT: The current python lib might not fully support high-level ModelCard objects easily yet or the API is verbose.
    # I will use a workaround or checks.
    # Actually, let's construct the BOM and then manually inject the modelCard data into the JSON if the library is tricky,
    # OR use the library's `model_card` property if it exists.

    # Let's check if we can assign model_card.
    # For this exercise, I will generate the BOM and then extend the JSON output manually
    # to ensure the `modelCard` matches the specific structure requested in Task A,
    # as the library's support for the full complexity of ModelCard might be complex to code in one pass without ref doc.
    # Update: cyclonedx-python-lib 6.0+ supports it.

    # I'll create the BOM with the component.
    bom.components.add(c)
    return bom

def main():
    parser = argparse.ArgumentParser(description="FRSCA-ML Provenance Generator")
    parser.add_argument("--dataset-url", required=True, help="URI of the dataset")
    parser.add_argument("--hyperparameters", required=True, help="JSON string of hyperparameters")
    parser.add_argument("--output-dir", required=True, help="Directory to save artifacts")

    args = parser.parse_args()

    # Parse Hyperparameters
    try:
        hp_dict = json.loads(args.hyperparameters)
        hp = Hyperparameters(**hp_dict)
    except Exception as e:
        print(f"Error parsing hyperparameters: {e}")
        hp = Hyperparameters()

    config = TrainingConfig(
        dataset_url=args.dataset_url,
        hyperparameters=hp,
        output_dir=args.output_dir
    )

    os.makedirs(config.output_dir, exist_ok=True)

    # 1. Simulate Training
    metrics = simulate_training()

    # 2. Generate Model Artifact
    model_path = os.path.join(config.output_dir, "model.pt")
    with open(model_path, "wb") as f:
        f.write(b"FAKE MODEL CONTENT " + str(metrics).encode())

    model_digest = calculate_sha256(model_path)

    # 3. Generate BOM
    bom = create_ai_bom(config, metrics, model_digest)
    output_formatter = JsonV1Dot6(bom)
    bom_json_str = output_formatter.output_as_string()

    # 4. Inject Model Card (Manual Patching for precision)
    # We do this to ensure the specific fields requested (quantitativeAnalysis) are present
    # even if the installed library version has a different API for ModelCard.
    bom_data = json.loads(bom_json_str)

    # Find the component
    for comp in bom_data.get("components", []):
        if comp.get("name") == "trained-model":
            comp["modelCard"] = {
                "modelParameters": {
                    "approach": { "type": "supervised" },
                    "task": "classification",
                    "hyperparameters": hp.model_dump(),
                    "datasets": [
                        {
                            "type": "dataset",
                            "name": "training-data",
                            "contents": {
                                "url": config.dataset_url
                            }
                        }
                    ]
                },
                "quantitativeAnalysis": {
                    "performanceMetrics": [
                        {"type": "accuracy", "value": str(metrics["accuracy"])},
                        {"type": "loss", "value": str(metrics["loss"])}
                    ]
                }
            }

    bom_path = os.path.join(config.output_dir, "cyclonedx.json")
    with open(bom_path, "w") as f:
        json.dump(bom_data, f, indent=2)

    print(f"Generated artifacts in {config.output_dir}")
    print(f"Model Digest: {model_digest}")
    print(f"Metrics: {metrics}")

    # 5. Write Tekton Results
    # Tekton expects results in /tekton/results/NAME
    # We check if /tekton/results exists, otherwise we just print
    results_dir = Path("/tekton/results")
    if results_dir.exists():
        (results_dir / "MODEL_DIGEST").write_text(model_digest)
        (results_dir / "TRAINING_METRICS").write_text(json.dumps(metrics))
        (results_dir / "AI_BOM_URI").write_text(f"file://{bom_path}")

if __name__ == "__main__":
    main()
