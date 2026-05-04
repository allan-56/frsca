"""
FRSCA-ML Airflow Integration

Provides a provenance-capturing Airflow operator for ML training tasks.

Usage:
    from frsca_ml_provenance.airflow_operator import FRSCAMLProvenanceOperator

    train_task = PythonOperator(
        task_id="train_model",
        python_callable=train_model,
    )

    provenance_task = FRSCAMLProvenanceOperator(
        task_id="capture_provenance",
        model_path="s3://models/model.safetensors",
        metrics="{{ ti.xcom_pull(task_ids='train_model', key='metrics') }}",
        params="{{ ti.xcom_pull(task_ids='train_model', key='params') }}",
        dataset_uri="s3://data/train.parquet",
    )

    train_task >> provenance_task
"""

import json
from typing import Optional

try:
    from airflow.models import BaseOperator
    from airflow.utils.decorators import apply_defaults

    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False


if AIRFLOW_AVAILABLE:

    class FRSCAMLProvenanceOperator(BaseOperator):
        """
        Airflow operator that captures provenance for a trained model.

        Parameters:
            model_path: S3/MinIO URI to the model artifact
            metrics: Training metrics (dict or XCom template string)
            params: Hyperparameters (dict or XCom template string)
            dataset_uri: URI to the training dataset
            s3_endpoint_url: MinIO endpoint URL
        """

        template_fields = ("metrics", "params", "dataset_uri")

        @apply_defaults
        def __init__(
            self,
            model_path: str,
            metrics: Optional[str] = None,
            params: Optional[str] = None,
            dataset_uri: Optional[str] = None,
            s3_endpoint_url: Optional[str] = None,
            *args,
            **kwargs,
        ):
            super().__init__(*args, **kwargs)
            self.model_path = model_path
            self.metrics = metrics
            self.params = params
            self.dataset_uri = dataset_uri
            self.s3_endpoint_url = s3_endpoint_url

        def execute(self, context):
            from .provenance_hook import capture

            metrics = self.metrics if isinstance(self.metrics, dict) else {}
            params = self.params if isinstance(self.params, dict) else {}

            if isinstance(self.metrics, str):
                try:
                    metrics = json.loads(self.metrics)
                except json.JSONDecodeError:
                    self.log.warning(f"Could not parse metrics: {self.metrics}")

            if isinstance(self.params, str):
                try:
                    params = json.loads(self.params)
                except json.JSONDecodeError:
                    self.log.warning(f"Could not parse params: {self.params}")

            self.log.info(f"Capturing provenance for: {self.model_path}")

            result = capture(
                model_path=self.model_path,
                metrics=metrics,
                params=params,
                dataset_uri=self.dataset_uri,
                builder_id="airflow",
                s3_endpoint_url=self.s3_endpoint_url,
            )

            self.log.info(f"Model SHA256: {result['artifact']['digest']}")
            return result

else:

    class FRSCAMLProvenanceOperator:
        """Placeholder when Airflow is not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Airflow is not installed. Install with: pip install apache-airflow"
            )
