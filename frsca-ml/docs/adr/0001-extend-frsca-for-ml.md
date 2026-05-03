<!-- markdownlint-disable MD013 -->
# 1. Extend FRSCA for Machine Learning (FRSCA-ML)

Date: 2024-04-27

## Status

Accepted

## Context

The Factory for Repeatable Secure Creation of Artifacts (FRSCA) currently
provides SLSA Level 3 compliance for traditional software artifacts (containers,
binaries). However, Machine Learning (ML) workflows introduce new artifact types
(models, datasets) and stochastic processes (training) that are not adequately
captured by standard SLSA build predicates.

Regulatory frameworks like the EU AI Act require detailed documentation of
training data, hyperparameters, and validation metrics. FRSCA's default "black
box" build observation fails to capture this semantic richness, leaving ML
models compliant in form (signed container) but opaque in substance (unknown
data lineage).

## Decision

We will extend the FRSCA architecture to support "FRSCA-ML" by:

* **Defining a custom in-toto predicate:**
  `https://frsca.dev/provenance/ml-training/v0.2` to capture ML-specific
  metadata (hyperparameters, metrics, dataset digests).

* **Integrating CycloneDX 1.6 AI-BOMs:**
  To represent the "Bill of Materials" for ML models, linking them to their
  training data and software dependencies.

* **Extending Tekton Chains with custom CUE templates:**
  To parse training results and generate the aforementioned attestations.

* **Implementing a "Data Provenance Controller" pattern:**
  (Conceptually) where data digests are verified before training.

## Consequences

### Positive

* **Regulatory Compliance:**
  Enables automated generation of documentation required by the EU AI Act
  (Annex IV) and NIST AI RMF.

* **Observability:**
  Provides visibility into the exact parameters and data used to train a
  specific model version.

* **Policy Enforcement:**
  Allows admission controllers (Kyverno) to make decisions based on model
  accuracy and data provenance, not just signature validity.

### Negative

* **Complexity:**
  Requires maintaining custom schemas and Tekton Chains configurations.

* **Storage Overhead:**
  Attestations and BOMs for large models can be significant; managing them in
  OCI registries requires OCI 1.1 reference type support or careful naming
  conventions.

* **Tooling Maturity:**
  CycloneDX 1.6 and ML-specific in-toto predicates are relatively new; tooling
  support (e.g., in visualization dashboards) may be nascent.
