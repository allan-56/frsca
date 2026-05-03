import argparse
import sys
from .ingest import run_ingest
from .extract import run_extract
from .train import run_train
from .evaluate import run_evaluate

def main():
    parser = argparse.ArgumentParser(description="FRSCA-ML Provenance Generator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest
    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--dataset-url", required=True)
    ingest_parser.add_argument("--output-dir", required=True)

    # Extract
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--dataset-url", required=True)
    extract_parser.add_argument("--feature-config", required=True)
    extract_parser.add_argument("--output-dir", required=True)

    # Train
    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--dataset-url", required=True)
    train_parser.add_argument("--feature-view-id", required=True)
    train_parser.add_argument("--hyperparameters", required=True)
    train_parser.add_argument("--output-dir", required=True)

    # Evaluate
    eval_parser = subparsers.add_parser("evaluate")
    eval_parser.add_argument("--model-digest", required=True)
    eval_parser.add_argument("--evaluation-data-url", required=True)
    eval_parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    if args.command == "ingest":
        run_ingest(args.dataset_url, args.output_dir)
    elif args.command == "extract":
        run_extract(args.dataset_url, args.feature_config, args.output_dir)
    elif args.command == "train":
        run_train(args.dataset_url, args.feature_view_id, args.hyperparameters, args.output_dir)
    elif args.command == "evaluate":
        run_evaluate(args.model_digest, args.evaluation_data_url, args.output_dir)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
