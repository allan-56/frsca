# FRSCA-ML Evaluation Results

## Overview

This document summarizes the evaluation of the FRSCA-ML security extension. The goal was to verify that the system correctly enforces security policies across the ML supply chain, preventing common attacks (STRIDE-AI/ATLAS).

## Scenarios Tested

The following scenarios were simulated and validated using the `frsca-ml/tests/validate_policies.py` test harness, which verifies Kyverno policies against generated in-toto attestations.

### S1: Unsigned / Invalid Model Deployment
*   **Goal:** Prevent deployment of models that lack valid signatures or attestations.
*   **Control:** Kyverno `verifyImages` rule (simulated by checking for missing attestations).
*   **Result:** **PASS** (Rejected deployments with no attestations).

### S3: Training on Unapproved Data
*   **Goal:** Prevent deployment of models trained on unauthorized datasets (e.g., PII, external sources).
*   **Control:** `require-dataset-provenance.yaml` checks that `predicate.mlSpecifics.datasets[0].uri` matches `s3://approved-data-bucket/*`.
*   **Result:** **PASS** (Rejected model claiming `s3://bad-bucket/data.csv`).

### S5: Manual Bypass / Missing Metadata
*   **Goal:** Prevent "shadow IT" deployments where a user manually deploys a pod without going through the pipeline.
*   **Control:** Kyverno policies require attestations to be present.
*   **Result:** **PASS** (Rejected resources with missing attestations).

### S8: Vulnerable Framework Version
*   **Goal:** Prevent deployment of models trained with vulnerable framework versions.
*   **Control:** `require-model-provenance.yaml` checks that `predicate.mlSpecifics.environment.frameworkVersion` matches `2.*`.
*   **Result:** **PASS** (Rejected model trained with version `1.5.0`).

### Metric Quality Gate
*   **Goal:** Prevent deployment of models that fail evaluation thresholds (e.g., accuracy < 0.85).
*   **Control:** `require-evaluation-provenance.yaml` checks `predicate.evaluationSpecifics.metrics.accuracy > 0.85`.
*   **Result:** **PASS** (Rejected model with accuracy `0.5`).

## Methodology

1.  **Predicate Generation:** Python scripts in `src/provenance_generator` were used to define the schema and structure of valid and invalid attestations.
2.  **Policy Validation:** A custom test harness (`tests/validate_policies.py`) loaded the Kyverno policy YAMLs and evaluated them against the JSON predicates.
3.  **Simulation:** "Attacks" were simulated by crafting predicates that violated specific policy rules (e.g., wrong URI, low accuracy).

## Conclusion

The FRSCA-ML policies successfully enforce the defined security properties. All simulated attack vectors were blocked by the policy engine.
