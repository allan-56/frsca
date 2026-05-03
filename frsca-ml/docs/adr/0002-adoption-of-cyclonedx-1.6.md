<!-- markdownlint-disable MD013 -->
# 2. Adoption of CycloneDX 1.6 for AI-BOMs

Date: 2024-04-27

## Status

Accepted

## Context

To secure the ML supply chain, we must provide a transparent record of the
model's components, including its software dependencies (libraries like PyTorch,
TensorFlow) and its data dependencies (training sets). We also need to document
"Model Card" information such as performance metrics and ethical
considerations.

Two primary standards exist for SBOMs: SPDX and CycloneDX.

* **SPDX 2.3** has some AI support but is historically focused on license
  compliance. SPDX 3.0 (RC) has rich AI profiles but is not yet finalized/widely
  supported.

* **CycloneDX 1.5** introduced `machine-learning-model` components and
  `modelCard` data. **CycloneDX 1.6** refined this support.

## Decision

We will adopt **CycloneDX 1.6** as the standard for AI-BOM generation in
FRSCA-ML.

## Consequences

### Positive

* **Native ML Support:**
  CycloneDX 1.6 has a dedicated `modelCard` object that maps directly to our
  requirements for capturing quantitative analysis and ethical considerations.

* **Unified Graph:**
  Allows representing the Model, the Dataset, and the Software Library in a
  single dependency graph (Model depends on Dataset).

* **Tooling:**
  The `cyclonedx-python-lib` has strong support for these features.

### Negative

* **Interoperability:**
  Some legacy tools may only support SPDX.

* **Verbosity:**
  The JSON files can become large when including full model card details.
