# Agent Instructions for FRSCA-ML

This document guides automated agents and human maintainers on how to work with
the FRSCA-ML codebase.

## System Components

1. **Schemas:** Located in `schemas/`. Defines the JSON structures for in-toto
   predicates and CycloneDX BOMs.

2. **Tekton:** Located in `tekton/`. Defines the CI/CD logic.
    * `tasks/model-training-task.yaml`: The core logic that runs the python
      script.
    * `pipelines/ml-supply-chain-pipeline.yaml`: The orchestrator.
    * `chains/provenance-template.cue`: The bridge between Tekton results and
      in-toto attestations.

3. **Policy:** Located in `policy/`. Kyverno rules to enforce security.

4. **Source:** `src/provenance_generator/`. The python code that simulates
   "training" and generates the raw BOM data.

## Validation Steps

### 1. Verify Schemas

Use a JSON schema validator to check that example artifacts conform to the
schemas in `schemas/`.

```bash
# Example
check-jsonschema \
  --schemafile schemas/in-toto/ml-training-predicate.json \
  examples/my-predicate.json
```

### 2. Run the Provenance Generator

To test the python logic without Tekton:

```bash
cd src/provenance_generator
pip install -r requirements.txt
python main.py \
  --dataset-url "s3://dummy/data" \
  --hyperparameters '{"epochs": 5}' \
  --output-dir ./out
```

Check `./out` for `model.pt` and `cyclonedx.json`.

### 3. Deploy to Kubernetes

Ensure you have a cluster with Tekton Pipelines, Tekton Chains, and Kyverno
installed.

1. Apply Tasks and Pipelines.

2. Configure Chains to use the CUE template (requires editing Chains ConfigMap).

3. Run the Pipeline.

## Day in the Life of a Packet

1. **Commit:** Data scientist pushes code.

2. **Tekton:** Pipeline starts. `git-clone` fetches code.

3. **Task:** `model-training-task` runs `main.py`.
    * `main.py` produces `model.pt` and `cyclonedx.json`.
    * Task outputs `MODEL_DIGEST`, `TRAINING_METRICS`, `AI_BOM_URI`.

4. **Chains:** Observes the TaskRun.
    * Signs the `model.pt` (simulated via OCI or blob signing).
    * Uses `provenance-template.cue` to create a signed SLSA attestation with
      ML specifics.
    * Attaches the `cyclonedx.json` as a statement or predicate.

5. **Registry:** Signed artifacts stored in OCI.

6. **Kyverno:** Admission controller checks `InferenceService`.
    * Verifies signature.
    * Checks Accuracy > 0.85 in the attestation.
    * Allows/Denies deployment.
