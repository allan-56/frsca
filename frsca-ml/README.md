# FRSCA-ML Extension

This directory contains the implementation of FRSCA extensions for Machine
Learning supply chain security.

## Components

- **Tekton Pipelines & Tasks:** Define the ML lifecycle stages (Ingest, Extract,
  Train, Evaluate).
- **Provenance Generator:** Python modules in `src/provenance_generator` that
  produce in-toto attestations for each stage.
- **Schemas:** Custom in-toto predicates in `schemas/in-toto`.
- **Kyverno Policies:** Security policies in `policy/kyverno` enforcing data
  provenance, model quality, and signed artifacts.
- **Tests:** Validation scripts in `tests/validate_policies.py` to simulate
  attack scenarios.

## Missing Implementations / Future Work

Per the project plan, the following integrations are deferred to future
iterations:

- **MLOps Tool Integration:** Integration with MLflow, Kubeflow, or other MLOps
  platforms to automatically trigger these pipelines or register models based on
  attestations.
- **Live Cluster Testing:** The current validation relies on a mocked policy
  engine (`tests/validate_policies.py`). End-to-end testing on a live
  Kubernetes cluster with Tekton Chains and Kyverno installed is required for
  production readiness.
- **Key Management:** Integration with Vault/SPIRE for signing key management in
  the ML context (currently using placeholder keys/checks).

## Running Tests

To validate the security policies against simulated attack scenarios:

```bash
python3 tests/validate_policies.py
```

See `evaluation_results.md` for detailed results of the security evaluation.
