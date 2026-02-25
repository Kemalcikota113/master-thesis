"""CLI entry point for c2rust single-pass pipeline."""

import argparse
from pathlib import Path

from c2rust import config
from c2rust.pipeline.single_pass import run_single_pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="Translate C projects to rough Rust and run compile-only checks.",
        epilog="Example: python -m c2rust.translate sds-master --provider openai --model gpt-4o",
    )
    parser.add_argument("dataset", help="Dataset folder name from datasets-c/")
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

    dataset_path = datasets_root / args.dataset
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        if datasets_root.exists():
            print("Available datasets:")
            for item in sorted(datasets_root.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    print(f"  - {item.name}")
        return 1

    print("\nConfiguration")
    print("-" * 70)
    print(f"Dataset: {args.dataset}")
    print(f"Provider: {config.get_provider_name()}")
    print(f"Model: {config.get_model_id()}")
    print("-" * 70)

    try:
        run_single_pass(args.dataset, datasets_root, output_root)
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
