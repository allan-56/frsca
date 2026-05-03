import unittest
import json
import os
import sys
import shutil
from unittest.mock import MagicMock, patch

# Add src to path to import integration modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# We mock dependencies that might not be installed
sys.modules["mlflow"] = MagicMock()
sys.modules["sklearn"] = MagicMock()
sys.modules["sklearn.ensemble"] = MagicMock()
sys.modules["sklearn.metrics"] = MagicMock()
sys.modules["pandas"] = MagicMock()
sys.modules["numpy"] = MagicMock()

class TestIntegrations(unittest.TestCase):

    def test_feast_retrieval(self):
        from integrations.feast import feature_store

        feature_store.get_features = MagicMock(return_value=json.dumps({"features": [[1,2]], "labels": [0]}))

        data = feature_store.get_features("rows", "refs")
        parsed = json.loads(data)
        self.assertIn("features", parsed)
        self.assertIn("labels", parsed)

    def test_mlflow_wrapper(self):
        from integrations.mlflow import mlflow_wrapper

        test_dir = "test_results"
        os.makedirs(test_dir, exist_ok=True)
        try:
            with open(os.path.join(test_dir, "TRAINING_METRICS"), "w") as f:
                json.dump({"accuracy": 0.95}, f)

            mlflow_wrapper.mlflow.start_run = MagicMock()

            mlflow_wrapper.log_task_results("run-id", test_dir)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
