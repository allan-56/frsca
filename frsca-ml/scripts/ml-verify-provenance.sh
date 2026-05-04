#!/usr/bin/env bash
set -euo pipefail

C_GREEN='\033[32m'
C_RED='\033[31m'
C_RESET_ALL='\033[0m'

# Verify Tekton Chains signing on FRSCA-ML pipeline TaskRuns.
# Usage: bash frsca-ml/scripts/ml-verify-provenance.sh [pipelinerun-name]
#
# If no pipelinerun name is given, uses --last.

PR_NAME="${1:-}"

echo -e "${C_GREEN}=== FRSCA-ML Provenance Verification ===${C_RESET_ALL}"

# Layer 1: Pipeline success
echo -e "${C_GREEN}Checking pipeline success...${C_RESET_ALL}"
if [ -n "${PR_NAME}" ]; then
  SUCCEEDED=$(tkn pr describe "${PR_NAME}" -o jsonpath='{.status.conditions[?(@.type == "Succeeded")].status}')
else
  SUCCEEDED=$(tkn pr describe --last -o jsonpath='{.status.conditions[?(@.type == "Succeeded")].status}')
fi
if [ "${SUCCEEDED}" != "True" ]; then
  echo -e "${C_RED}Pipeline did not succeed.${C_RESET_ALL}"
  exit 1
fi
echo -e "${C_GREEN}  Pipeline succeeded.${C_RESET_ALL}"

# Get child TaskRuns
if [ -n "${PR_NAME}" ]; then
  TASK_RUNS_JSON=$(tkn pr describe "${PR_NAME}" -o jsonpath='{.status.childReferences}')
else
  TASK_RUNS_JSON=$(tkn pr describe --last -o jsonpath='{.status.childReferences}')
fi
TASK_RUNS=$(echo "${TASK_RUNS_JSON}" | jq -r '.[] | select(.kind | match("TaskRun")) | .name')

# Layer 2: Tekton Chains signing annotation on each TaskRun
echo -e "${C_GREEN}Checking Tekton Chains signing annotations...${C_RESET_ALL}"
SIGNED_COUNT=0
TOTAL_COUNT=0
for tr in ${TASK_RUNS}; do
  TOTAL_COUNT=$((TOTAL_COUNT + 1))
  SIGNED=$(kubectl get taskrun "${tr}" -o jsonpath='{.metadata.annotations.chains\.tekton\.dev/signed}' 2>/dev/null || echo "")
  if [ "${SIGNED}" == "true" ]; then
    echo -e "${C_GREEN}  TaskRun ${tr}: SIGNED${C_RESET_ALL}"
    SIGNED_COUNT=$((SIGNED_COUNT + 1))
  else
    echo -e "${C_RED}  TaskRun ${tr}: NOT SIGNED${C_RESET_ALL}"
  fi
done

# Layer 3: Verify TaskRun attestation signatures with cosign
echo -e "${C_GREEN}Verifying TaskRun attestation signatures...${C_RESET_ALL}"
VERIFIED_COUNT=0
for tr in ${TASK_RUNS}; do
  TR_UID=$(kubectl get taskrun "${tr}" -o jsonpath='{.metadata.uid}')
  SIGNATURE_ANNOTATION="chains.tekton.dev/signature-taskrun-${TR_UID}"
  SIGNATURE=$(kubectl get taskrun "${tr}" -o jsonpath="{.metadata.annotations.${SIGNATURE_ANNOTATION}}" 2>/dev/null || echo "")

  if [ -z "${SIGNATURE}" ]; then
    echo -e "${C_RED}  TaskRun ${tr}: No signature annotation found${C_RESET_ALL}"
    continue
  fi

  echo "${SIGNATURE}" | base64 --decode > "/tmp/sig-${tr}.pub" 2>/dev/null || true

  # Create a payload from the TaskRun for verification
  kubectl get taskrun "${tr}" -o json | jq -r '.metadata.annotations["chains.tekton.dev/payload-taskrun-'"${TR_UID}"'"]' | base64 --decode > "/tmp/payload-${tr}.json" 2>/dev/null || true

  if [ -s "/tmp/sig-${tr}.pub" ] && [ -s "/tmp/payload-${tr}.json" ]; then
    if cosign verify-blob \
      --key k8s://tekton-chains/signing-secrets \
      --signature "/tmp/sig-${tr}.pub" \
      "/tmp/payload-${tr}.json" >/dev/null 2>&1; then
      echo -e "${C_GREEN}  TaskRun ${tr}: Signature VERIFIED${C_RESET_ALL}"
      VERIFIED_COUNT=$((VERIFIED_COUNT + 1))
    else
      echo -e "${C_RED}  TaskRun ${tr}: Signature verification FAILED${C_RESET_ALL}"
    fi
  else
    echo -e "${C_RED}  TaskRun ${tr}: Could not extract signature/payload${C_RESET_ALL}"
  fi

  rm -f "/tmp/sig-${tr}.pub" "/tmp/payload-${tr}.json"
done

# Summary
echo ""
echo -e "${C_GREEN}=== Verification Summary ===${C_RESET_ALL}"
echo -e "  Pipeline succeeded:     ${SUCCEEDED}"
echo -e "  TaskRuns signed:        ${SIGNED_COUNT}/${TOTAL_COUNT}"
echo -e "  Signatures verified:    ${VERIFIED_COUNT}/${TOTAL_COUNT}"

if [ "${SUCCEEDED}" == "True" ] && [ "${SIGNED_COUNT}" -eq "${TOTAL_COUNT}" ] && [ "${VERIFIED_COUNT}" -eq "${TOTAL_COUNT}" ]; then
  echo -e "${C_GREEN}All verifications passed.${C_RESET_ALL}"
  exit 0
else
  echo -e "${C_RED}Some verifications failed.${C_RESET_ALL}"
  exit 1
fi
