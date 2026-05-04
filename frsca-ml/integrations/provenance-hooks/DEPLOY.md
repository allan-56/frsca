# Deploying FRSCA-ML into an Existing ML Platform

## Architecture Overview

FRSCA-ML doesn't replace your existing ML platform. It wraps around it as a
**security and provenance layer** that intercepts artifacts, signs them, and
enforces policies at deployment time.

```
YOUR EXISTING PLATFORM                    FRSCA-ML LAYER
─────────────────────                    ──────────────

┌──────────┐                             ┌──────────────┐
│ MLflow   │──log model──▶              │ Provenance   │
│ Tracking │               ┌───────────▶│ Hook         │
└──────────┘               │            │ (hash+sign)  │
                           │            └──────┬───────┘
┌──────────┐               │                   │
│ Ray /    │──train────▶   │                   ▼
│ KubeRay  │               │            ┌──────────────┐
└──────────┘               │            │ Tekton       │
                           │            │ Chains       │
┌──────────┐               │            │ (sign)       │
│ Airflow  │──orchestrate─▶│            └──────┬───────┘
└──────────┘               │                   │
                           │                   ▼
┌──────────┐               │            ┌──────────────┐
│ MinIO /  │◀──store──────┘            │ SPDX SBOM    │
│ S3       │                            │ + Attestation│
└──────┬───┘                            └──────────────┘
       │                                        │
       │ upload model                           │
       ▼                                        ▼
┌──────────┐                            ┌──────────────┐
│ Model    │◀───── Kyverno check ──────│ Kyverno      │
│ Serving  │       (attestation?)       │ Policy       │
│ (KServe) │                            │ Engine       │
└──────────┘                            └──────────────┘
```

## Deployment Steps

### Step 1: Deploy FRSCA-ML Provenance Infrastructure

```bash
# On your existing Kubernetes cluster that runs ML workloads
make setup-frsca-core    # Tekton Pipelines + Chains + Kyverno
make setup-example-ml    # FRSCA-ML tasks and pipelines
```

This installs:
- Tekton Pipelines (pipeline engine)
- Tekton Chains (automatic signing)
- Kyverno (policy enforcement)
- FRSCA-ML tasks, policies, and validation scripts

### Step 2: Deploy the MinIO Provenance Webhook

The webhook watches your MinIO buckets for new model artifacts and
automatically computes SHA256 hashes and generates attestations.

```bash
# Create the namespace
kubectl create namespace ml-platform --dry-run=client -o yaml | kubectl apply -f -

# Create MinIO credentials secret
kubectl create secret generic minio-credentials \
  --from-literal=access-key=YOUR_ACCESS_KEY \
  --from-literal=secret-key=YOUR_SECRET_KEY \
  -n ml-platform

# Deploy the webhook
kubectl apply -f frsca-ml/integrations/provenance-hooks/deploy/webhook-deployment.yaml
```

The webhook will:
1. Watch `models` and `checkpoints` buckets
2. When a `.safetensors`, `.bin`, `.pt`, `.onnx`, or `.pkl` file appears
3. Compute its SHA256 hash
4. Generate a provenance attestation
5. Store the attestation in the `attestations` bucket

### Step 3: Integrate with Your Training Code

#### Option A: Python Hook (MLflow + Ray)

Add one function call after training:

```python
import mlflow
from frsca_ml_provenance import capture

# Your existing training code
with mlflow.start_run() as run:
    model = train_model(...)
    metrics = evaluate_model(model, test_data)

    # Save model as safetensors
    from safetensors.torch import save_file
    save_file(model.state_dict(), "model.safetensors")

    # Upload to MinIO
    upload_to_minio("model.safetensors", "models/team/model.safetensors")

    # === ADD THIS: Capture provenance ===
    capture(
        model_path="s3://models/team/model.safetensors",
        mlflow_run_id=run.info.run_id,
        metrics={"accuracy": metrics["accuracy"], "loss": metrics["loss"]},
        params={"epochs": 10, "lr": 0.001, "batch_size": 32},
        dataset_uri="s3://data/train.parquet",
        s3_endpoint_url="http://minio:9000",
    )
```

#### Option B: Ray/KubeRay Training

```python
import ray
from ray.train.torch import TorchTrainer
from frsca_ml_provenance.ray_wrapper import wrap_ray_trainer

# Wrap the trainer
SecureTorchTrainer = wrap_ray_trainer(TorchTrainer)

trainer = SecureTorchTrainer(
    train_loop_per_worker=train_func,
    scaling_config=ray.train.ScalingConfig(num_workers=4),
    # FRSCA-ML parameters
    frsca_model_path="s3://models/team/model.safetensors",
    frsca_dataset_uri="s3://data/train.parquet",
)

result = trainer.fit()
# Provenance is automatically captured after training
```

#### Option C: Airflow DAG

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from frsca_ml_provenance.airflow_operator import FRSCAMLProvenanceOperator

with DAG("ml_training_pipeline", schedule_interval="@daily") as dag:

    train = PythonOperator(
        task_id="train",
        python_callable=train_model,
    )

    provenance = FRSCAMLProvenanceOperator(
        task_id="capture_provenance",
        model_path="s3://models/team/model.safetensors",
        metrics="{{ ti.xcom_pull(task_ids='train', key='metrics') }}",
        params="{{ ti.xcom_pull(task_ids='train', key='params') }}",
        dataset_uri="s3://data/train.parquet",
    )

    train >> provenance
```

#### Option D: No Code Changes (MinIO-only)

If you can't modify training code, the MinIO webhook handles everything:

1. Training code uploads model to MinIO (as usual)
2. Webhook detects the new artifact
3. Webhook computes hash and generates attestation
4. Attestation stored alongside the model

No code changes required. The webhook is fully automatic.

### Step 4: Configure Model Serving with Policy Enforcement

Label your model serving pods to trigger Kyverno policy checks:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: model-serving
  namespace: ml-prod
spec:
  template:
    metadata:
      labels:
        frsca.ml/model: "true"   # ← Triggers Kyverno policy
      annotations:
        frsca.ml/attestation-uri: "s3://attestations/models/team/model.safetensors.attestation.json"
        frsca.ml/model-sha256: "2d86b6bd767d7e6b..."
    spec:
      containers:
        - name: model-server
          image: model-server:latest
```

Kyverno will:
- Check that `frsca.ml/attestation-uri` annotation exists
- Check that `frsca.ml/model-sha256` annotation exists
- Block deployment if either is missing

### Step 5: Verify the Full Chain

```bash
# Check that attestations were generated
mc ls minio/attestations/models/team/

# Verify a specific attestation
mc cat minio/attestations/models/team/model.safetensors.attestation.json | jq .

# Check Kyverno policy status
kubectl get clusterpolicy frsca-ml-require-model-attestation -o yaml

# Test enforcement (should be blocked)
kubectl run test-model --image=model-server:latest \
  -l frsca/ml/model=true \
  --dry-run=server   # Should fail without attestation annotations

# Run FRSCA-ML provenance verification
bash frsca-ml/scripts/ml-verify-provenance.sh
```

## Integration Points Summary

| Your System | FRSCA-ML Integration | Change Required |
|---|---|---|
| **MLflow Tracking** | `provenance_hook.capture()` after `log_model()` | Add 5 lines |
| **MinIO/S3** | Webhook watches buckets automatically | No code change |
| **Ray/KubeRay** | `wrap_ray_trainer()` or `capture_ray_provenance()` | Add 3 lines |
| **Airflow** | `FRSCAMLProvenanceOperator` in DAG | Add 1 operator |
| **KServe/Seldon** | Kyverno policy checks annotations at deploy time | Add labels |
| **Tekton Chains** | Signs TaskRuns automatically (installed by FRSCA) | No code change |

## What Gets Captured

For every model artifact, FRSCA-ML records:

```
Attestation (in-toto v0.1):
├── buildDefinition
│   ├── buildType: "https://frsca.dev/ml/build/v1"
│   ├── modelPath: "s3://models/team/model.safetensors"
│   ├── datasetUri: "s3://data/train.parquet"
│   └── hyperparameters: {epochs: 10, lr: 0.001}
├── runDetails
│   ├── builder.id: "mlflow" | "kuberay" | "airflow" | "ml-platform"
│   └── metadata: {startedOn, finishedOn}
├── mlSpecifics
│   ├── environment: {framework: "pytorch", version: "2.4.0"}
│   ├── metrics: {accuracy: 0.92, loss: 0.08}
│   └── datasets: [{name, uri, digest}]
└── outputArtifacts
    └── [{name, uri, sha256, sizeBytes, mediaType}]

SPDX 3.0.1 AI Profile:
├── AIPackage (model)
│   ├── verifiedUsing: SHA256
│   ├── typeOfModel, domain, hyperparameter, metric
│   └── safetyRiskAssessment, standardCompliance
├── DatasetPackage
├── Build
└── Relationships: verifiedUsing, trainedOn, builtBy
```

## Scaling This Deployment

For production use across many teams:

1. **Namespace per team**: Each team gets its own namespace with its own
   EventListener and Kyverno policy exceptions.

2. **Centralized signing**: Tekton Chains runs in `tekton-chains` namespace
   and signs all TaskRuns cluster-wide.

3. **Shared MinIO**: One MinIO instance serves all teams. The webhook watches
   all model buckets. Attestations stored per-team:
   ```
   s3://attestations/team-alpha/model.safetensors.attestation.json
   s3://attestations/team-beta/model.safetensors.attestation.json
   ```

4. **Policy per environment**: Different Kyverno policies for dev/staging/prod:
   ```yaml
   # dev: warn only
   validationFailureAction: Audit
   # prod: block
   validationFailureAction: Enforce
   ```

5. **Registry as single source of truth**: Push signed images to a central
   registry. Kyverno verifies signatures at pull time.
