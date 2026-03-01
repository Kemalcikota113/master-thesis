"""CLI entry point for pilot APR experiment."""

import argparse
from pathlib import Path

from c2rust import config
from c2rust.apr.runner import run_apr_experiment


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run translation + APR strategy experiment for C->Rust datasets.",
        epilog=(
            "Example: python -m c2rust.apr_experiment sds-master cjson/cJSON-master "
            "--max-attempts 5 --provider openai --model gpt-4o"
        ),
    )
    parser.add_argument(
        "datasets",
        nargs="+",
        help="Dataset folder names from datasets-c/ (can include nested paths)",
    )
    parser.add_argument("--max-attempts", type=int, default=5, help="Max APR attempts per strategy")
    parser.add_argument(
        "--use-existing-translation",
        action="store_true",
        help="Skip translation stage and use existing output/<dataset>-rust artifacts",
    )
    parser.add_argument(
        "--apply-prepass",
        action="store_true",
        help="Apply deterministic APR prepass (macro hoisting) before attempt loop",
    )
    parser.add_argument("--provider", choices=["openai", "gemini"], help="LLM provider override")
    parser.add_argument("--model", help="Model id override")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.provider:
        config.MODEL_PROVIDER = args.provider
    if args.model:
        config.MODEL_ID = args.model

    project_root = Path(__file__).parent.parent
    datasets_root = project_root / "datasets-c"
    output_root = project_root / "output"
    experiments_root = project_root / "experiments"

    print("\nExperiment Configuration")
    print("-" * 70)
    print(f"Datasets: {', '.join(args.datasets)}")
    print(f"Provider: {config.get_provider_name()}")
    print(f"Model: {config.get_model_id()}")
    print(f"Max attempts: {args.max_attempts}")
    print(f"Use existing translation: {args.use_existing_translation}")
    print(f"Apply APR prepass: {args.apply_prepass}")
    print("-" * 70)

    try:
        run_apr_experiment(
            datasets=args.datasets,
            datasets_root=datasets_root,
            output_root=output_root,
            experiments_root=experiments_root,
            max_attempts=args.max_attempts,
            use_existing_translation=args.use_existing_translation,
            apply_prepass=args.apply_prepass,
        )
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as exc:
        print(f"\nError: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
