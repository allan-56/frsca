# FRSCA-ML System Architecture and Scaling Guide

## Table of Contents

1. [System Overview](#system-overview)
2. [Pipeline Execution Flow (Input → Processing → Output)](#pipeline-execution-flow)
3. [Provenance and Attestation Chain](#provenance-and-attestation-chain)
4. [Artifact Validation](#artifact-validation)
5. [SPDX AI Profile Generation](#spdx-ai-profile-generation)
6. [Kyverno Policy Enforcement](#kyverno-policy-enforcement)
7. [Hugging Face Example Walkthrough](#hugging-face-example-walkthrough)
8. [Scaling to ~1000 Repositories](#scaling-to-1000-repositories)

---

## System Overview

FRSCA-ML extends the FRSCA (Factory for Repeatable Secure Creation of Artifacts) platform
to secure Machine Learning supply chains. It ensures that every ML model artifact is:

- **Trained** inside auditable Tekton pipelines
- **Signed** by Tekton Chains with SLSA provenance
- **Validated** against binary integrity (SHA256 hash)
- **Documented** in SPDX 3.0.1 AI profile format
- **Enforced** at deploy time via Kyverno admission policies

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRSCA-ML Platform                           │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  Git Push │──▶│ Tekton   │──▶│ Chains   │──▶│ Kyverno  │    │
│  │ (trigger) │   │ Pipeline │   │ (sign)   │   │ (enforce)│    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│                      │               │               │          │
│                      ▼               ▼               ▼          │
│               ┌──────────┐   ┌──────────┐   ┌──────────┐       │
│               │ .safe-   │   │ SLSA     │   │ Block or │       │
│               │ tensors  │   │ Prov-    │   │ Allow    │       │
│               │ artifact │   │ enance   │   │ Deploy   │       │
│               └──────────┘   └──────────┘   └──────────┘       │
│                      │               │                          │
│                      ▼               ▼                          │
│               ┌──────────────────────────┐                     │
│               │  SPDX 3.0.1 AI SBOM      │                     │
│               │  (model + dataset + hash) │                     │
│               └──────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Execution Flow

### The ML Supply Chain Pipeline

```
ml-supply-chain-pipeline
│
├── 1. fetch-source          (git-clone Task)
│       INPUT:  git-url, git-revision
│       OUTPUT: source code in workspace
│
├── 2. ingest-data            (data-ingestion-task)
│       INPUT:  dataset-url (e.g. s3://bucket/data.csv)
│       PROCESS:
│         - Download dataset from S3/HTTP
│         - Validate schema
│         - Check for PII
│         - Compute SHA256 digest
│       OUTPUT: DATA_SNAPSHOT_ID, DATA_DIGEST, ATTESTATION_URI
│
├── 3. extract-features       (feature-extraction-task)
│       INPUT:  dataset-url, feature-config
│       PROCESS:
│         - Transform raw data into feature vectors
│         - Generate feature view ID
│         - Create extraction attestation
│       OUTPUT: FEATURE_VIEW_ID, ATTESTATION_URI
│
├── 4. train-model            (model-training-task)
│       INPUT:  dataset-url, feature-view-id, hyperparameters
│       PROCESS:
│         - Run ML training (PyTorch/TensorFlow)
│         - Save model artifact (.safetensors)
│         - Compute model SHA256 digest
│         - Generate training metrics (accuracy, loss)
│         - Create training attestation
│       OUTPUT: MODEL_DIGEST, TRAINING_METRICS, ATTESTATION_URI
│
└── 5. evaluate-model         (model-evaluation-task)
        INPUT:  model-digest, evaluation-data-url
        PROCESS:
          - Load trained model
          - Run evaluation on held-out data
          - Compute metrics (accuracy, loss)
          - Check pass/fail threshold
          - Create evaluation attestation
        OUTPUT: EVALUATION_METRICS, PASSED, ATTESTATION_URI
```

### Data Flow Between Stages

```
Stage 1 (git-clone)
  └─▶ workspace/source/ contains repo with frsca-ml/src/

Stage 2 (ingest)
  ├─▶ workspace/outputs/ingest/dataset.csv         (downloaded data)
  ├─▶ workspace/outputs/ingest/ingest_attestation.json
  └─▶ Results: DATA_SNAPSHOT_ID, DATA_DIGEST

Stage 3 (extract)
  ├─▶ workspace/outputs/extract/feature_attestation.json
  └─▶ Results: FEATURE_VIEW_ID ──────────────┐
                                              │
Stage 4 (train)                               │
  ├─◀─────────────────────────────────────────┘ (uses FEATURE_VIEW_ID)
  ├─▶ workspace/outputs/train/model.pt
  ├─▶ workspace/outputs/train/training_attestation.json
  └─▶ Results: MODEL_DIGEST ─────────────────┐
                                              │
Stage 5 (evaluate)                            │
  ├─◀─────────────────────────────────────────┘ (uses MODEL_DIGEST)
  ├─▶ workspace/outputs/evaluate/evaluation_attestation.json
  └─▶ Results: EVALUATION_METRICS, PASSED
```

### What Each Task Produces

Each task writes results to `/tekton/results/` which Tekton makes available
to downstream tasks and the pipeline controller:

```
/tekton/results/
├── DATA_SNAPSHOT_ID      "snap-a1b2c3d4"
├── DATA_DIGEST           "sha256:e3b0c44298fc..."
├── FEATURE_VIEW_ID       "features-9f8e7d6c"
├── MODEL_DIGEST          "sha256:2d86b6bd767d..."
├── TRAINING_METRICS      '{"accuracy":0.88,"loss":0.15}'
├── EVALUATION_METRICS    '{"accuracy":0.92,"loss":0.08}'
├── PASSED                "true"
└── ATTESTATION_URI       "/workspace/outputs/train/attestation.json"
```

---

## Provenance and Attestation Chain

### How Tekton Chains Signs TaskRuns

After each TaskRun completes, Tekton Chains:

```
1. Observes the TaskRun completion
2. Collects:
   - Task definition (image, script, params)
   - Input artifacts (workspace contents, params)
   - Output artifacts (results, images)
   - Build metadata (start time, end time, builder ID)
3. Creates an in-toto attestation (SLSA v1 format)
4. Signs it with the configured key (cosign/Vault)
5. Stores:
   - Annotation: chains.tekton.dev/signed = "true"
   - Payload:   chains.tekton.dev/payload-taskrun-{UID} = base64(attestation)
   - Signature: chains.tekton.dev/signature-taskrun-{UID} = base64(sig)
   - OCI:       Pushes to registry (if IMAGE_URL result exists)
```

### Attestation Structure (per TaskRun)

```json
{
  "_type": "https://in-toto.io/Statement/v0.1",
  "predicateType": "https://slsa.dev/provenance/v0.2",
  "subject": [{
    "name": "model.safetensors",
    "digest": {"sha256": "2d86b6bd767d..."}
  }],
  "predicate": {
    "builder": {
      "id": "https://tekton.dev/chains/v2"
    },
    "buildType": "tekton.dev/v1beta1/TaskRun",
    "invocation": {
      "configSource": {
        "uri": "git+https://github.com/buildsec/frsca",
        "digest": {"sha256": "abc123..."}
      }
    },
    "materials": [{
      "uri": "python:3.12-slim",
      "digest": {"sha256": "..."}
    }]
  }
}
```

### ML-Specific Provenance (FRSCA extension)

The ML tasks also generate an extended attestation:

```json
{
  "predicateType": "https://frsca.dev/provenance/ml-training/v0.2",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://frsca.dev/ml/build/v1",
      "externalParameters": {
        "datasetUrl": "s3://approved-data/train.csv",
        "featureViewId": "features-9f8e7d6c",
        "hyperparameters": {"epochs": 5, "lr": 0.01}
      }
    },
    "mlSpecifics": {
      "hyperparameters": {"epochs": 5, "lr": 0.01},
      "environment": {
        "framework": "pytorch",
        "frameworkVersion": "2.0.1"
      },
      "metrics": {"accuracy": 0.88, "loss": 0.15},
      "datasets": [{
        "name": "training-data",
        "uri": "s3://approved-data/train.csv",
        "digest": {"sha256": "..."}
      }]
    },
    "outputArtifacts": [{
      "name": "model.safetensors",
      "uri": "file:///workspace/outputs/train/model.safetensors",
      "digest": {"sha256": "2d86b6bd767d..."},
      "sizeBytes": 264000000,
      "mediaType": "application/vnd.safetensors"
    }]
  }
}
```

---

## Artifact Validation

### Binary Hash Validation for .safetensors

The SafeTensor format is validated in three steps:

```
Step 1: Type Detection
  ├─ Extension check: .safetensors → application/vnd.safetensors
  └─ Magic bytes:    first 8 bytes = b"sf_tensors"

Step 2: Header Parsing
  ├─ Read 8-byte little-endian header size
  ├─ Read header JSON (contains tensor metadata)
  ├─ Validate JSON structure
  └─ Extract: tensor count, names, shapes, data offsets

Step 3: Integrity Hash
  └─ SHA256 of entire file (header + tensor data)
```

### SafeTensor File Format

```
Offset 0:     [8 bytes] Header size (little-endian uint64)
Offset 8:     [N bytes] Header JSON
Offset 8+N:   [M bytes] Tensor data (contiguous binary)

Header JSON:
{
  "layer.weight": {
    "dtype": "F32",
    "shape": [768, 3072],
    "data_offsets": [0, 9437184]
  },
  "layer.bias": {
    "dtype": "F32",
    "shape": [3072],
    "data_offsets": [9437184, 9449472]
  },
  "__metadata__": {
    "format": "pt"
  }
}
```

### Validation Output

```json
{
  "filepath": "/workspace/model.safetensors",
  "filename": "model.safetensors",
  "size_bytes": 264000000,
  "sha256": "2d86b6bd767d7e6b6b2fb977a7ca9223e7a3035dc7ebff0e077e6fc515b72476",
  "artifact_type": "application/vnd.safetensors",
  "valid": true,
  "format_validation": {
    "valid": true,
    "tensor_count": 67,
    "tensor_names": ["embeddings.weight", "embeddings.bias", ...],
    "total_bytes": 263700000,
    "metadata": {"format": "pt"}
  }
}
```

---

## SPDX AI Profile Generation

### What Gets Documented

```
SPDX Document: "distilbert-imdb-sbom"
│
├── AIPackage: "distilbert-finetuned-imdb"
│   ├── packageVersion: "1.0.0"
│   ├── downloadLocation: "https://huggingface.co/.../model.safetensors"
│   ├── verifiedUsing: [Hash(algorithm="sha256", value="2d86b6...")]
│   ├── typeOfModel: ["transformer"]
│   ├── domain: ["nlp", "sentiment-analysis"]
│   ├── hyperparameter: [
│   │     {key: "epochs", value: "3"},
│   │     {key: "batch_size", value: "8"},
│   │     {key: "learning_rate", value: "5e-5"}
│   │   ]
│   ├── metric: [
│   │     {key: "eval_accuracy", value: "0.92"},
│   │     {key: "eval_loss", value: "0.21"}
│   │   ]
│   ├── informationAboutTraining: "Fine-tuned on IMDB using HF Transformers"
│   ├── safetyRiskAssessment: "low"
│   └── standardCompliance: ["EU AI Act", "NIST AI RMF"]
│
├── DatasetPackage: "imdb"
│   ├── packageVersion: "1.0"
│   ├── downloadLocation: "https://huggingface.co/datasets/imdb"
│   ├── verifiedUsing: [Hash(algorithm="sha256", value="b2c3d4...")]
│   ├── datasetType: "text"
│   └── hasSensitivePersonalInformation: "no"
│
├── Build: "frsca-hf-finetune-task"
│   ├── buildType: "https://frsca.dev/ml/build/v1"
│   ├── buildStartTime: "2026-05-04T10:00:00Z"
│   ├── buildEndTime: "2026-05-04T10:15:00Z"
│   └── parameter: [{key: "epochs", value: "3"}, ...]
│
└── Relationships:
      distilbert-finetuned-imdb --verifiedUsing--> sha256:2d86b6...
      distilbert-finetuned-imdb --trainedOn-->     dataset-imdb
      distilbert-finetuned-imdb --builtBy-->       build-frsca-hf-finetune
      distilbert-finetuned-imdb --hasDeclaredLicense--> Apache-2.0
```

### SPDX 3.0.1 AI Profile Classes Used

| SPDX Class | Purpose | Cardinality |
|---|---|---|
| `AIPackage` | The trained model | 1 per model |
| `DatasetPackage` | Training/eval data | 1+ per pipeline |
| `Build` | Training run metadata | 1 per pipeline |
| `Hash` | SHA256 of binary artifacts | 1+ per package |
| `DictionaryEntry` | Hyperparameters, metrics | 0-N per package |
| `Relationship` | Links between elements | 1+ per document |
| `SpdxDocument` | Top-level container | 1 per SBOM |

---

## Kyverno Policy Enforcement

### Policy: require-ai-bom-and-accuracy

Blocks deployment of model images unless:

```
Rule 1: Training Provenance Required
  ├─ MATCH:   InferenceService resources
  ├─ VERIFY:  attestation type = https://frsca.dev/provenance/ml-training/v0.2
  └─ CONDITION: predicate.mlSpecifics.metrics.accuracy > 0.85

Rule 2: AI-BOM Required
  ├─ MATCH:   InferenceService resources
  ├─ VERIFY:  attestation type = https://cyclonedx.org/bom
  └─ CONDITION: predicate.components[?type=='machine-learning-model'] > 0
```

### Enforcement Flow

```
Developer deploys model
  │
  ▼
Kubernetes API Server
  │
  ▼
Kyverno Admission Webhook
  │
  ├── Check: Does the image have a training attestation?
  │   ├── YES → Extract accuracy metric
  │   │         ├── accuracy > 0.85? → Continue
  │   │         └── accuracy ≤ 0.85? → REJECT
  │   └── NO  → REJECT
  │
  ├── Check: Does the image have an AI-BOM attestation?
  │   ├── YES → Has ML model component? → Continue
  │   └── NO  → REJECT
  │
  └── All checks pass → ALLOW deployment
```

### Additional Policies

| Policy | Enforces |
|---|---|
| `require-dataset-provenance` | Dataset URI must be from approved bucket |
| `require-model-provenance` | Builder must be `frsca-training-task`, framework version `2.*` |
| `require-evaluation-provenance` | `passed == true` and `accuracy > 0.85` |

---

## Hugging Face Example Walkthrough

### What It Does

Fine-tunes `distilbert-base-uncased` for sentiment analysis on the IMDB dataset.

### Step-by-Step

```
Step 1: Install Dependencies
  └─ pip install transformers datasets safetensors torch

Step 2: Load Model and Tokenizer
  ├─ AutoTokenizer.from_pretrained("distilbert-base-uncased")
  └─ AutoModelForSequenceClassification.from_pretrained(..., num_labels=2)

Step 3: Load and Prepare Dataset
  ├─ load_dataset("imdb", split="train[:500]")
  ├─ tokenize(text → input_ids, attention_mask)
  └─ train_test_split(test_size=0.2)

Step 4: Train
  ├─ Trainer(model, args, train_dataset, eval_dataset)
  └─ trainer.train() → {train_loss, train_runtime, ...}

Step 5: Evaluate
  └─ trainer.evaluate() → {eval_loss, eval_accuracy}

Step 6: Save as SafeTensors
  ├─ save_file(model.state_dict(), "model.safetensors")
  └─ Compute SHA256 of the file

Step 7: Generate Provenance
  ├─ Training attestation (hyperparams, metrics, environment)
  └─ Output artifact record (name, uri, sha256, size, mediaType)

Step 8: Write Tekton Results
  ├─ /tekton/results/MODEL_DIGEST      → sha256:...
  ├─ /tekton/results/MODEL_PATH        → /workspace/model-output/model.safetensors
  ├─ /tekton/results/TRAINING_METRICS  → {"accuracy":0.92,...}
  └─ /tekton/results/ATTESTATION_URI   → /workspace/outputs/finetune/attestation.json
```

### Input/Output Summary

```
INPUTS:
  ├── Source:     https://github.com/buildsec/frsca (git clone)
  ├── Model:      distilbert-base-uncased (from HuggingFace Hub)
  ├── Dataset:    imdb (from HuggingFace Hub, 500 samples)
  ├── Hyperparams: epochs=1, batch_size=8, lr=5e-5
  └── Container:  python:3.12-slim

OUTPUTS:
  ├── model.safetensors     (fine-tuned weights, ~264MB, SHA256-validated)
  ├── metrics.json          (train_loss, eval_loss, eval_accuracy, train_runtime)
  ├── attestation.json      (full in-toto provenance with all inputs/outputs)
  └── Tekton results        (MODEL_DIGEST, MODEL_PATH, TRAINING_METRICS, ATTESTATION_URI)

VERIFICATION:
  ├── Tekton Chains signs the TaskRun → chains.tekton.dev/signed=true
  ├── SLSA provenance stored in OCI registry
  ├── SHA256 of model.safetensors matches MODEL_DIGEST result
  └── SPDX SBOM documents model, dataset, build, and hash
```

---

## Scaling to ~1000 Repositories

### Current Architecture (Single Pipeline)

```
Git Push → EventListener → TriggerTemplate → PipelineRun → Signed Artifacts
```

### Scaling Challenges

| Challenge | Single Repo | 1000 Repos |
|---|---|---|
| Pipeline concurrency | 1-2 at a time | 100+ concurrent |
| Tekton Chains signing | Per TaskRun | 500+ TaskRuns/hour |
| Kyverno policy eval | Trivial | 1000+ admission checks/hour |
| Registry storage | MBs | TBs of models |
| Attestation storage | Few attestations | 5000+ attestations |
| GitOps management | Manual | Automated |

### Scaling Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitOps Control Plane                      │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ ArgoCD / │  │ Tekton   │  │ Chains   │  │ Kyverno  │   │
│  │ Flux     │  │ (scaled) │  │ (scaled) │  │ (scaled) │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│              Kubernetes Cluster (multi-node)                 │
│                                                             │
│  Namespace: frsca-ml-team-a     Namespace: frsca-ml-team-b  │
│  ┌─────────────────┐           ┌─────────────────┐         │
│  │ PipelineRun x 5  │           │ PipelineRun x 5  │         │
│  │ (parallel)       │           │ (parallel)       │         │
│  └─────────────────┘           └─────────────────┘         │
│                                                             │
│  Namespace: frsca-ml-team-c     ... (up to 100 teams)       │
│  ┌─────────────────┐                                        │
│  │ PipelineRun x 5  │                                        │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Shared Services                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Gitea    │  │ Registry │  │ Vault    │  │ SPIRE    │   │
│  │ (mirror) │  │ (OCI)    │  │ (KMS)    │  │ (identity)│  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Step 1: Multi-Tenant Namespaces

```yaml
# One namespace per team/project
apiVersion: v1
kind: Namespace
metadata:
  name: frsca-ml-team-alpha
  labels:
    frsca.ml/managed: "true"
    frsca.ml/team: "alpha"
```

Each namespace gets:
- Its own Tekton Triggers EventListener
- Its own ServiceAccount + RBAC
- Its own Kyverno policy exceptions (if needed)

### Step 2: Pipeline Parallelism

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: ml-pipeline-
spec:
  pipelineRef:
    name: ml-supply-chain-pipeline
  taskRunTemplate:
    podTemplate:
      nodeSelector:
        frsca.ml/gpu: "false"   # CPU-only for data tasks
```

Tekton's default controller handles concurrent PipelineRuns. For 1000 repos:

```
Concurrent PipelineRuns:  ~100 (limited by cluster resources)
TaskRuns per Pipeline:    5
Concurrent TaskRuns:      ~500
```

Scale the Tekton controller:
```bash
kubectl scale deployment tekton-pipelines-controller -n tekton-pipelines --replicas=3
```

### Step 3: Chains Scaling

```yaml
# chains-config ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: chains-config
  namespace: tekton-chains
data:
  artifacts.taskrun.storage: "oci"       # Store in registry (not annotations)
  artifacts.taskrun.format: "slsa/v1"    # SLSA provenance format
  transparency.enabled: "true"           # Rekor transparency log
  storage.oci.repository: "registry.example.com/attestations"
```

For 1000 repos with 5 TaskRuns each = 5000 attestations:
- Storage: ~500MB (each attestation ~100KB)
- Signing: 5000 cosign operations
- Use `oci` storage to avoid annotation size limits

### Step 4: Registry Architecture

```
registry.example.com/
├── models/
│   ├── team-alpha/
│   │   ├── model-v1.safetensors    (264MB)
│   │   └── model-v2.safetensors    (264MB)
│   ├── team-beta/
│   │   └── model-v1.safetensors    (132MB)
│   └── ...
├── attestations/
│   ├── team-alpha/
│   │   ├── model-v1.att            (SLSA provenance)
│   │   └── model-v1.ai-bom         (CycloneDX AI-BOM)
│   └── ...
└── base-images/
    └── python/3.12-slim             (shared base)
```

Storage estimate for 1000 repos:
- Models: 1000 × 264MB = ~264GB
- Attestations: 5000 × 100KB = ~500MB
- Total: ~265GB (use object storage backend)

### Step 5: GitOps Automation

```yaml
# ArgoCD ApplicationSet for auto-provisioning
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: frsca-ml-repos
spec:
  generators:
    - git:
        repoURL: https://github.com/org/ml-repos-manifest
        revision: main
        directories:
          - path: "repos/*"
  template:
    metadata:
      name: "frsca-ml-{{path.basename}}"
    spec:
      project: frsca-ml
      source:
        repoURL: https://github.com/org/ml-repos-manifest
        path: "{{path}}"
        targetRevision: main
      destination:
        server: https://kubernetes.default.svc
        namespace: "frsca-ml-{{path.basename}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

### Step 6: Auto-Provisioning Script

```bash
#!/usr/bin/env bash
# provisions a new ML repo into the FRSCA-ML platform

REPO_NAME="$1"
TEAM_NAME="$2"
NAMESPACE="frsca-ml-${TEAM_NAME}"

# 1. Create namespace
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# 2. Create ServiceAccount
kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: pipeline-account
  namespace: ${NAMESPACE}
EOF

# 3. Install triggers for this repo
cat <<EOF | kubectl apply -f -
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: ${REPO_NAME}-listener
  namespace: ${NAMESPACE}
spec:
  serviceAccountName: pipeline-account
  triggers:
    - name: ml-pipeline
      bindings:
        - ref: ml-pipeline-binding
      template:
        ref: ml-pipeline-template
EOF

# 4. Mirror repo to Gitea
curl -X POST "https://gitea-http:3000/api/v1/orgs/${TEAM_NAME}/repos" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"${REPO_NAME}\", \"auto_init\": false}"

# 5. Create webhook
curl -X POST "https://gitea-http:3000/api/v1/repos/${TEAM_NAME}/${REPO_NAME}/hooks" \
  -H "Content-Type: application/json" \
  -d "{\"config\": {\"url\": \"http://el-${REPO_NAME}-listener.${NAMESPACE}:8080\", \"content_type\": \"json\"}}"
```

### Step 7: Monitoring at Scale

```
┌─────────────────────────────────────────────────┐
│              Grafana Dashboard                    │
│                                                  │
│  Pipeline Success Rate    TaskRun Duration        │
│  ████████████░░ 85%      ██████░░░░ 2.5min avg   │
│                                                  │
│  Signing Status           Policy Rejections       │
│  ██████████████ 99%      █░░░░░░░░░ 2%           │
│                                                  │
│  Active PipelineRuns: 47   Queued: 12             │
│  Registry Usage: 187GB     Attestations: 3,847    │
└─────────────────────────────────────────────────┘
```

### Scaling Summary

| Dimension | Strategy | Target |
| --- | --- | --- |
| **Repos** | Auto-provision via GitOps | 1000+ |
| **Concurrency** | Multi-namespace + parallel PipelineRuns | 100 concurrent |
| **Signing** | OCI storage + controller replicas | 5000/hour |
| **Storage** | Object storage backend (S3/GCS) | TB-scale |
| **Policies** | Namespace-scoped exceptions | Per-team overrides |
| **Provisioning** | ApplicationSet + shell automation | Zero-touch |
| **Monitoring** | Prometheus + Grafana | Real-time |
| **Cost** | Spot/preemptible nodes for training | 70% savings |
