#!/usr/bin/env bash
set -euo pipefail

C_GREEN='\033[32m'
C_RESET_ALL='\033[0m'

: "${REPO_URL:=https://github.com/${GITHUB_REPOSITORY:-buildsec/frsca}}"
: "${COMMIT_SHA:=$(git rev-parse HEAD 2>/dev/null || echo main)}"
: "${DATASET_URL:=https://example.com/dummy/dataset.csv}"
: "${EVAL_DATA_URL:=https://example.com/dummy/eval.csv}"

echo -e "${C_GREEN}Starting ML Supply Chain Pipeline...${C_RESET_ALL}"
tkn pipeline start ml-supply-chain-pipeline \
  --param git-url="${REPO_URL}" \
  --param git-revision="${COMMIT_SHA}" \
  --param dataset-url="${DATASET_URL}" \
  --param evaluation-data-url="${EVAL_DATA_URL}" \
  --param context-dir="frsca-ml" \
  --workspace name=shared-workspace,volumeClaimTemplateFile=platform/tekton/pvc.yaml \
  --use-param-defaults \
  --showlog
