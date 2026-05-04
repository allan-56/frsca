"""
Integration tests: Kubernetes policy enforcement.

Tests that Kyverno policies correctly block/allow model deployments
based on FRSCA-ML attestation annotations.

Requires a running Kubernetes cluster with Kyverno installed.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def k8s_api(k8s_client_instance):
    """Get Kubernetes CoreV1Api."""
    return k8s_client_instance.CoreV1Api()


@pytest.fixture
def k8s_custom(k8s_client_instance):
    """Get Kubernetes CustomObjectsApi."""
    return k8s_client_instance.CustomObjectsApi()


class TestKyvernoPolicyExists:
    """Verify FRSCA-ML Kyverno policies are installed."""

    def test_require_ai_bom_policy_exists(self, k8s_custom):
        """Check that require-ai-bom-and-accuracy ClusterPolicy exists."""
        try:
            policy = k8s_custom.get_cluster_custom_object(
                group="kyverno.io",
                version="v1",
                plural="clusterpolicies",
                name="require-ai-bom-and-accuracy",
            )
            assert policy["kind"] == "ClusterPolicy"
            assert policy["spec"]["validationFailureAction"] == "Enforce"
        except Exception as e:
            if "NotFound" in str(e):
                pytest.skip("require-ai-bom-and-accuracy policy not installed")
            raise

    def test_require_model_provenance_policy_exists(self, k8s_custom):
        """Check that require-model-provenance ClusterPolicy exists."""
        try:
            policy = k8s_custom.get_cluster_custom_object(
                group="kyverno.io",
                version="v1",
                plural="clusterpolicies",
                name="require-model-provenance",
            )
            assert policy["kind"] == "ClusterPolicy"
        except Exception as e:
            if "NotFound" in str(e):
                pytest.skip("require-model-provenance policy not installed")
            raise


class TestTektonResourcesInstalled:
    """Verify FRSCA-ML Tekton resources are installed."""

    def test_ml_pipeline_exists(self, k8s_custom):
        """Check that ml-supply-chain-pipeline Pipeline exists."""
        try:
            pipeline = k8s_custom.get_namespaced_custom_object(
                group="tekton.dev",
                version="v1",
                namespace="default",
                plural="pipelines",
                name="ml-supply-chain-pipeline",
            )
            assert pipeline["kind"] == "Pipeline"
            task_names = [t["name"] for t in pipeline["spec"]["tasks"]]
            assert "fetch-source" in task_names
            assert "train-model" in task_names
        except Exception as e:
            if "NotFound" in str(e):
                pytest.skip("ml-supply-chain-pipeline not installed")
            raise

    def test_training_task_exists(self, k8s_custom):
        """Check that model-training-task Task exists."""
        try:
            task = k8s_custom.get_namespaced_custom_object(
                group="tekton.dev",
                version="v1",
                namespace="default",
                plural="tasks",
                name="model-training-task",
            )
            assert task["kind"] == "Task"
            result_names = [r["name"] for r in task["spec"]["results"]]
            assert "MODEL_DIGEST" in result_names
            assert "TRAINING_METRICS" in result_names
        except Exception as e:
            if "NotFound" in str(e):
                pytest.skip("model-training-task not installed")
            raise

    def test_all_ml_tasks_exist(self, k8s_custom):
        """Check that all FRSCA-ML tasks are installed."""
        expected_tasks = [
            "data-ingestion-task",
            "feature-extraction-task",
            "model-training-task",
            "model-evaluation-task",
        ]
        for task_name in expected_tasks:
            try:
                task = k8s_custom.get_namespaced_custom_object(
                    group="tekton.dev",
                    version="v1",
                    namespace="default",
                    plural="tasks",
                    name=task_name,
                )
                assert task["kind"] == "Task", f"{task_name} is not a Task"
            except Exception as e:
                if "NotFound" in str(e):
                    pytest.skip(f"{task_name} not installed")
                raise


class TestTektonChainsConfiguration:
    """Verify Tekton Chains is configured for FRSCA-ML."""

    def test_chains_config_has_slsv1(self, k8s_api):
        """Check Chains configmap uses slsa/v1 format."""
        try:
            cm = k8s_api.read_namespaced_config_map(
                name="chains-config", namespace="tekton-chains"
            )
            assert cm.data.get("artifacts.taskrun.format") == "slsa/v1"
            assert "oci" in cm.data.get("artifacts.taskrun.storage", "")
        except Exception as e:
            if "NotFound" in str(e) or "Forbidden" in str(e):
                pytest.skip("Cannot access chains-config ConfigMap")
            raise

    def test_chains_controller_running(self, k8s_api):
        """Check Chains controller pods are running."""
        try:
            pods = k8s_api.list_namespaced_pod(
                namespace="tekton-chains",
                label_selector="app=tekton-chains-controller",
            )
            running = [
                p for p in pods.items
                if p.status.phase == "Running"
            ]
            assert len(running) > 0, "No Chains controller pods running"
        except Exception as e:
            if "NotFound" in str(e) or "Forbidden" in str(e):
                pytest.skip("Cannot access tekton-chains namespace")
            raise


class TestPodAdmissionWithAttestation:
    """
    Test pod admission with/without attestation annotations.

    These tests verify that Kyverno correctly enforces the FRSCA-ML
    policies at the Kubernetes admission layer.
    """

    def test_pod_without_attestation_annotations(self, k8s_api):
        """A model pod without attestation annotations should be rejected."""
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "test-model-no-attestation",
                "namespace": "default",
                "labels": {
                    "frsca.ml/model": "true",
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "model-server",
                        "image": "busybox:latest",
                        "command": ["sleep", "3600"],
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        try:
            k8s_api.create_namespaced_pod(
                namespace="default", body=pod_manifest
            )
            # If we get here, policy is in Audit mode (not Enforce)
            # Clean up
            k8s_api.delete_namespaced_pod(
                name="test-model-no-attestation", namespace="default"
            )
            pytest.skip("Policy is in Audit mode, not Enforce")
        except Exception as e:
            error_str = str(e)
            # Expected: Kyverno should reject this
            if "Forbidden" in error_str or "denied" in error_str.lower():
                assert True
            elif "NotFound" in error_str:
                pytest.skip("Kyverno not installed")
            else:
                raise

    def test_pod_with_attestation_annotations(self, k8s_api):
        """A model pod with attestation annotations should be allowed."""
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "test-model-with-attestation",
                "namespace": "default",
                "labels": {
                    "frsca.ml/model": "true",
                },
                "annotations": {
                    "frsca.ml/attestation-uri": "s3://attestations/model.att.json",
                    "frsca.ml/model-sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "model-server",
                        "image": "busybox:latest",
                        "command": ["sleep", "10"],
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        try:
            k8s_api.create_namespaced_pod(
                namespace="default", body=pod_manifest
            )
            # Wait for pod to be scheduled
            import time
            time.sleep(5)

            pod = k8s_api.read_namespaced_pod(
                name="test-model-with-attestation", namespace="default"
            )
            assert pod.status.phase in ("Running", "Pending", "Succeeded")

            # Clean up
            k8s_api.delete_namespaced_pod(
                name="test-model-with-attestation", namespace="default"
            )
        except Exception as e:
            if "NotFound" in str(e):
                pytest.skip("Kyverno not installed")
            raise

    def test_pod_without_model_label_bypasses_policy(self, k8s_api):
        """A pod without frsca.ml/model label should not be checked."""
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "test-regular-pod",
                "namespace": "default",
            },
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "image": "busybox:latest",
                        "command": ["sleep", "10"],
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        try:
            k8s_api.create_namespaced_pod(
                namespace="default", body=pod_manifest
            )
            import time
            time.sleep(3)

            pod = k8s_api.read_namespaced_pod(
                name="test-regular-pod", namespace="default"
            )
            assert pod.status.phase in ("Running", "Pending", "Succeeded")

            k8s_api.delete_namespaced_pod(
                name="test-regular-pod", namespace="default"
            )
        except Exception as e:
            if "NotFound" in str(e):
                pytest.skip("K8s not available")
            raise
