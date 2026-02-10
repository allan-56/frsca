import argparse
import mlflow
import json
import os

def log_task_results(run_id: str, results_dir: str):
    """
    Logs results from a Tekton Task (stored in /tekton/results or similar) to MLflow.
    """
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow-server:5000"))

    print(f"Logging to MLflow Run: {run_id}")

    with mlflow.start_run(run_id=run_id):
        # 1. Log Metrics (e.g. accuracy, loss)
        metrics_file = os.path.join(results_dir, "TRAINING_METRICS")
        if os.path.exists(metrics_file):
            try:
                with open(metrics_file, "r") as f:
                    content = f.read().strip()
                    # Try parsing as JSON first
                    try:
                        metrics = json.loads(content)
                        for k, v in metrics.items():
                            mlflow.log_metric(k, float(v))
                    except json.JSONDecodeError:
                        # Fallback: maybe just key=value lines?
                        pass
            except Exception as e:
                print(f"Error logging metrics: {e}")

        # 2. Log Artifacts (e.g. BOM, provenance)
        # In a real scenario, we might upload the actual files.
        # Here we just log parameters pointing to them.

        # 3. Log Parameters
        # ...

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--results-dir", default="/tekton/results")
    args = parser.parse_args()

    log_task_results(args.run_id, args.results_dir)
