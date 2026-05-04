"""
FRSCA-ML Ray Training Wrapper

Wraps Ray Train workers to automatically capture provenance.

Usage:
  from frsca_ml_provenance.ray_wrapper import frsca_ray_trainer

  # Instead of:
  #   trainer = TorchTrainer(train_func, ...)
  # Use:
  #   trainer = frsca_ray_trainer(train_func, model_output_path="s3://models/...", ...)
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional


def capture_ray_provenance(
    model_path: str,
    metrics: dict,
    params: dict,
    dataset_uri: Optional[str] = None,
    s3_endpoint_url: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """
    Capture provenance from a Ray training job.

    Call this at the end of your Ray train function:

        def train_func():
            # ... distributed training ...
            torch.save(model.state_dict(), "model.safetensors")

            # Capture provenance
            from frsca_ml_provenance.ray_wrapper import capture_ray_provenance
            capture_ray_provenance(
                model_path="s3://models/model.safetensors",
                metrics={"accuracy": accuracy},
                params={"lr": lr, "epochs": epochs},
            )
    """
    from .provenance_hook import capture

    return capture(
        model_path=model_path,
        metrics=metrics,
        params=params,
        dataset_uri=dataset_uri,
        builder_id="kuberay",
        framework="pytorch",
        s3_endpoint_url=s3_endpoint_url,
        output_dir=output_dir,
    )


def wrap_ray_trainer(trainer_class):
    """
    Decorator that wraps a Ray Trainer class to auto-capture provenance.

    Usage:
        from ray.train.torch import TorchTrainer
        from frsca_ml_provenance.ray_wrapper import wrap_ray_trainer

        SecureTorchTrainer = wrap_ray_trainer(TorchTrainer)

        trainer = SecureTorchTrainer(
            train_loop_per_worker=train_func,
            ...
            frsca_model_path="s3://models/model.safetensors",
            frsca_dataset_uri="s3://data/train.parquet",
        )
    """

    class WrappedTrainer(trainer_class):
        def __init__(self, *args, frsca_model_path=None, frsca_dataset_uri=None, **kwargs):
            super().__init__(*args, **kwargs)
            self._frsca_model_path = frsca_model_path
            self._frsca_dataset_uri = frsca_dataset_uri

        def fit(self):
            result = super().fit()
            if self._frsca_model_path:
                metrics = {}
                if hasattr(result, "metrics"):
                    metrics = result.metrics or {}
                capture_ray_provenance(
                    model_path=self._frsca_model_path,
                    metrics=metrics,
                    params={},
                    dataset_uri=self._frsca_dataset_uri,
                )
            return result

    WrappedTrainer.__name__ = trainer_class.__name__
    WrappedTrainer.__qualname__ = trainer_class.__qualname__
    return WrappedTrainer
