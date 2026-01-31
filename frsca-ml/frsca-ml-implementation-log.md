# FRSCA-ML Implementation Log

## Overview
This log documents the implementation process of the FRSCA-ML extension.

## Step 1: Define Data Schemas
- Created directory structure under `frsca-ml/`.
- Initialized this log file.
- Created `frsca-ml/schemas/in-toto/ml-training-predicate.json` (Draft-07 schema).
- Created `frsca-ml/schemas/in-toto/dataset-provenance.json` (Draft-07 schema).
- Created `frsca-ml/schemas/cyclone-dx/ai-bom-1.6-template.json` (CycloneDX 1.6 example).

## Step 2: Tekton Configuration (The "Body")
- Created `frsca-ml/tekton/tasks/model-training-task.yaml`.
- Created `frsca-ml/tekton/pipelines/ml-supply-chain-pipeline.yaml`.
- Created `frsca-ml/tekton/chains/provenance-template.cue`.

## Step 3: Policy Enforcement (The "Gate")
- Created `frsca-ml/policy/kyverno/require-ai-bom.yaml`.
- Created `frsca-ml/deploy/inference-service.yaml`.

## Step 4: Provenence Generator Tool (The "Glue")
- Created `frsca-ml/src/provenance_generator/requirements.txt`.
- Created `frsca-ml/src/provenance_generator/main.py`.

## Step 5: Documentation (The "Memory")
- Created `frsca-ml/docs/adr/0001-extend-frsca-for-ml.md`.
- Created `frsca-ml/docs/adr/0002-adoption-of-cyclonedx-1.6.md`.
- Created `frsca-ml/docs/agent-instructions.md`.
- Created `frsca-ml/docs/pipeline-execution.md`.

## Step 6: CI Configuration
- Updated `model-training-task.yaml` and `ml-supply-chain-pipeline.yaml` to support `context-dir`.
- Created `.github/workflows/ci-frsca-ml.yaml`.

## Step 7: Verification
- Validated `src/provenance_generator/main.py` by running it in the sandbox.
- Verified BOM generation output.
- Cleaned up test artifacts (`frsca-ml/test-out`).
