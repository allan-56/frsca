#!/usr/bin/env bash
set -euo pipefail

C_GREEN='\033[32m'
C_RESET_ALL='\033[0m'

GIT_ROOT=$(git rev-parse --show-toplevel)

echo -e "${C_GREEN}Installing FRSCA-ML Tekton Tasks...${C_RESET_ALL}"
kubectl apply -f "${GIT_ROOT}"/frsca-ml/tekton/tasks/

echo -e "${C_GREEN}Installing FRSCA-ML Pipelines...${C_RESET_ALL}"
kubectl apply -f "${GIT_ROOT}"/frsca-ml/tekton/pipelines/

echo -e "${C_GREEN}Configuring Tekton Chains for FRSCA-ML...${C_RESET_ALL}"
kubectl patch configmap chains-config -n tekton-chains \
  -p '{"data":{"artifacts.taskrun.format":"slsa/v1","artifacts.taskrun.storage":"oci","transparency.enabled":"true"}}'
kubectl delete pod -n tekton-chains -l app=tekton-chains-controller --ignore-not-found
kubectl wait --for=condition=ready pod -l app=tekton-chains-controller -n tekton-chains --timeout=300s

echo -e "${C_GREEN}FRSCA-ML setup complete.${C_RESET_ALL}"
