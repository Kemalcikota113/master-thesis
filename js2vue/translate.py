"""
CLI entry point for the JS-to-Vue translation framework.

Usage:
    python -m js2vue.translate <dataset> [--mode single|multi] [--provider openai|gemini]

Examples:
    python -m js2vue.translate todomvc-es6 --mode single
    python -m js2vue.translate realworld-js --mode multi --provider gemini
    python -m js2vue.translate framework-bench --mode single --model gpt-4o
"""

import argparse
import sys
from pathlib import Path

from js2vue import config
from js2vue.pipeline.single_pass import run_single_pass
from js2vue.pipeline.multi_pass import run_multi_pass


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Translate JavaScript projects to Vue 3 with TypeScript",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s todomvc-es6 --mode single
  %(prog)s realworld-js --mode multi
  %(prog)s framework-bench --mode single --provider gemini

Available datasets:
  - todomvc-es6
  - realworld-js
  - framework-bench
  - realworld-backend
        """
    )

    parser.add_argument(
        "dataset",
        help="Name of the dataset to translate (must exist in datasets/)"
    )

    parser.add_argument(
        "--mode",
        choices=["single", "multi"],
        default="single",
        help="Translation mode: 'single' (baseline) or 'multi' (with APRA) [default: single]"
    )

    parser.add_argument(
        "--provider",
        choices=["openai", "gemini"],
        help=f"LLM provider [default: {config.MODEL_PROVIDER}]"
    )

    parser.add_argument(
        "--model",
        help=f"Model ID to use [default: {config.MODEL_ID}]"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        help=f"Maximum repair iterations [default: {config.MAX_REPAIR_ITERATIONS}]"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Update config if overrides provided
    if args.provider:
        config.MODEL_PROVIDER = args.provider
    if args.model:
        config.MODEL_ID = args.model
    if args.max_iterations:
        config.MAX_REPAIR_ITERATIONS = args.max_iterations

    # Resolve paths
    project_root = Path(__file__).parent.parent
    datasets_root = project_root / "datasets"
    output_root = project_root / "output"

    dataset_path = datasets_root / args.dataset

    # Validate dataset exists
    if not dataset_path.exists():
        print(f"❌ Error: Dataset '{args.dataset}' not found at {dataset_path}")
        print(f"\nAvailable datasets:")
        if datasets_root.exists():
            for item in sorted(datasets_root.iterdir()):
                if item.is_dir() and not item.name.startswith('.'):
                    print(f"  - {item.name}")
        sys.exit(1)

    # Print configuration
    print("\n" + "=" * 70)
    print("CONFIGURATION")
    print("=" * 70)
    print(f"Dataset: {args.dataset}")
    print(f"Mode: {args.mode}")
    print(f"Provider: {config.get_provider_name()}")
    print(f"Model: {config.get_model_id()}")
    print(f"Max iterations: {config.get_max_iterations()}")
    print("=" * 70 + "\n")

    try:
        # Run appropriate pipeline
        if args.mode == "single":
            metrics = run_single_pass(args.dataset, datasets_root, output_root)
        else:  # multi
            metrics = run_multi_pass(args.dataset, datasets_root, output_root)

        # Print final summary table
        print("\n" + "=" * 70)
        print("FINAL RESULTS")
        print("=" * 70)
        print(f"{'Metric':<40} {'Value':>25}")
        print("-" * 70)
        print(f"{'Dataset':<40} {metrics.dataset_name:>25}")
        print(f"{'Pipeline Mode':<40} {metrics.pipeline_mode:>25}")
        print(f"{'Files Translated':<40} {metrics.files_translated:>25}")
        print(f"{'Files with Errors':<40} {metrics.files_with_errors:>25}")
        print(f"{'Initial Error Count':<40} {metrics.initial_error_count:>25}")
        print(f"{'Final Error Count':<40} {metrics.final_error_count:>25}")

        if metrics.error_reduction_factor != float('inf'):
            erf_display = f"{metrics.error_reduction_factor:.2f}x"
        else:
            erf_display = "∞ (perfect)"
        print(f"{'Error Reduction Factor':<40} {erf_display:>25}")

        print(f"{'Template-Script Coherence Errors':<40} {metrics.template_script_coherence_errors:>25}")
        print(f"{'Repair Iterations':<40} {metrics.repair_iterations:>25}")
        print(f"{'Total Tokens Used':<40} {metrics.tokens_used['total']:>25,}")
        print(f"{'Time (seconds)':<40} {metrics.timing_seconds:>25.1f}")
        print(f"{'Model Provider':<40} {metrics.model_provider:>25}")
        print(f"{'Model ID':<40} {metrics.model_id:>25}")
        print("=" * 70)

        # Print output location
        output_dir = output_root / f"{args.dataset}-vue"
        print(f"\n📂 Output directory: {output_dir}")
        print(f"📊 Metrics file: {output_dir / 'metrics.json'}")

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Translation interrupted by user")
        return 130

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
