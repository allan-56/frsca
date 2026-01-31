# FRSCA-ML Pipeline Execution Guide

This guide details how to execute the FRSCA-ML pipeline and verify the results.

## Prerequisites

*   Kubernetes Cluster (Minikube, Kind, or Cloud).
*   Tekton Pipelines installed.
*   Tekton Chains installed.
*   Kyverno installed.
*   `kubectl` and `tkn` CLI tools.
*   Python 3.9+ (for local testing).

## Step 1: Install FRSCA-ML Components

Apply the Tekton resources:

```bash
kubectl apply -f tekton/tasks/model-training-task.yaml
kubectl apply -f tekton/pipelines/ml-supply-chain-pipeline.yaml
```

Apply the Policy:

```bash
kubectl apply -f policy/kyverno/require-ai-bom.yaml
```

## Step 2: Configure Tekton Chains

To use the custom CUE template, you must configure Tekton Chains.
(Note: In a real setup, you would patch the `chains-config` ConfigMap).

1.  Store the CUE template in a ConfigMap:
    ```bash
    kubectl create configmap frsca-ml-cue --from-file=provenance=tekton/chains/provenance-template.cue -n tekton-chains
    ```
2.  Configure Chains to use it:
    ```bash
    kubectl patch configmap chains-config -n tekton-chains -p '{"data":{"artifacts.taskrun.format":"cue", "artifacts.taskrun.storage":"oci", "transparency.enabled": "true"}}'
    ```

## Step 3: Run the Pipeline

Start the pipeline using `tkn`:

```bash
tkn pipeline start ml-supply-chain-pipeline \
  --param git-url="https://github.com/example/frsca-ml-repo" \
  --param dataset-url="s3://public-datasets/mnist.csv" \
  --param hyperparameters='{"epochs": 10, "lr": 0.001}' \
  --workspace name=shared-workspace,volumeClaimTemplateFile=pvc.yaml \
  --showlog
```
(Ensure you provide a valid PVC yaml or use `emptyDir` for testing).

## Step 4: Verification

### 1. Retrieve the Attestation
Once the pipeline finishes, find the image/artifact digest.
Use `cosign` to verify:

```bash
# Verify signature
cosign verify --key k8s://tekton-chains/signing-secrets <IMAGE_URI>

# Verify Attestation
cosign verify-attestation --type https://frsca.dev/provenance/ml-training/v0.2 \
  --key k8s://tekton-chains/signing-secrets \
  <IMAGE_URI>
```

### 2. Verify Policy
Try to apply the InferenceService:

```bash
kubectl apply -f deploy/inference-service.yaml
```

*   **Success:** If the image is signed and accuracy > 0.85, the resource is created.
*   **Failure:** If the image is unsigned or accuracy is low, Kyverno blocks it with a message.

## Troubleshooting
*   **Chains Logs:** `kubectl logs -n tekton-chains -l app=tekton-chains-controller`
*   **Pipeline Logs:** `tkn pr logs -L`
