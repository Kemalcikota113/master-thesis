"""run_pilot.py — Main orchestrator for the APR v2 pilot experiment.

Usage examples
--------------
# Translate and run all 4 strategies on sds-master:
python run_pilot.py sds-master --max-attempts 10

# Skip translation (reuse existing output/) and run two datasets:
python run_pilot.py sds-master kilo-master --use-existing-translation

# Override model:
python run_pilot.py sds-master --provider openai --model gpt-4o --max-attempts 10

Pipeline
--------
For each dataset:
  1. Translate C → Rust once via the existing single-pass pipeline
     (or reuse output/<dataset>-rust if --use-existing-translation).
  2. Check the fidelity gate; skip APR if gate failed.
  3. Copy the translated baseline into 4 isolated per-strategy directories.
  4. Run each APR strategy independently for up to max_attempts iterations.
  5. Write results to experiments/<timestamp>/results.jsonl (one line per run)
     and experiments/<timestamp>/attempts.csv (one row per attempt).
  6. Generate matplotlib plots in experiments/<timestamp>/plots/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

# Ensure the repo root is on the path when called directly.
sys.path.insert(0, str(Path(__file__).parent))

from c2rust import config
from c2rust.apr.runner_v2 import RunResult, create_agents, run_strategy_v2
from c2rust.apr.strategies import AprStrategyV2
from c2rust.pipeline.single_pass import run_single_pass
from c2rust.plot_pilot_v2 import generate_plots


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="APR v2 pilot: compare 4 prompting strategies for C→Rust compile-error repair.",
        epilog=(
            "Example: python run_pilot.py sds-master kilo-master "
            "--max-attempts 10 --provider openai --model gpt-4o"
        ),
    )
    parser.add_argument(
        "datasets",
        nargs="+",
        help="Dataset folder names from datasets-c/ (e.g. sds-master kilo-master)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=10,
        help="Maximum APR iterations per strategy (default: 10)",
    )
    parser.add_argument(
        "--use-existing-translation",
        action="store_true",
        help="Skip translation and reuse existing output/<dataset>-rust artifacts",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini"],
        help="LLM provider override",
    )
    parser.add_argument(
        "--model",
        help="Model ID override (e.g. gpt-4o)",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=[s.value for s in AprStrategyV2],
        default=None,
        help="Run only the specified strategies (default: all four)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Translation stage
# ---------------------------------------------------------------------------

def _load_or_run_translation(
    dataset: str,
    datasets_root: Path,
    output_root: Path,
    use_existing: bool,
) -> tuple[bool, bool]:
    """Return (fidelity_gate_passed, compile_success).

    If use_existing=True, reads metrics.json from the existing output directory.
    Otherwise runs the full translation pipeline.
    """
    output_dir = output_root / f"{dataset}-rust"

    if use_existing:
        metrics_path = output_dir / "metrics.json"
        if not metrics_path.exists():
            print(f"  [!] Missing metrics.json at {metrics_path} — cannot use existing translation.")
            return False, False
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        gate = bool(data.get("fidelity_gate_passed", False))
        compiled = bool(data.get("compile_success", False))
        print(f"  Loaded existing translation. Gate: {gate}, Compiled: {compiled}")
        return gate, compiled

    print("  Running translation pipeline...")
    metrics = run_single_pass(dataset, datasets_root, output_root)
    return metrics.fidelity_gate_passed, metrics.compile_success


# ---------------------------------------------------------------------------
# Per-strategy run
# ---------------------------------------------------------------------------

def _run_one_strategy(
    strategy: AprStrategyV2,
    dataset: str,
    translated_dir: Path,
    experiments_dir: Path,
    max_attempts: int,
    repair_agent,
    diagnose_agent,
    attempts_csv: Path,
) -> RunResult:
    """Copy the baseline, run the strategy loop, return RunResult."""
    strategy_project_dir = (
        experiments_dir / "projects" / dataset.replace("/", "__") / strategy.value / "project"
    )
    if strategy_project_dir.exists():
        shutil.rmtree(strategy_project_dir)
    strategy_project_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(translated_dir, strategy_project_dir)

    print(f"    Strategy: {strategy.value}")
    result = run_strategy_v2(
        strategy=strategy,
        dataset=dataset,
        project_dir=strategy_project_dir,
        experiments_dir=experiments_dir,
        max_attempts=max_attempts,
        repair_agent=repair_agent,
        diagnose_agent=diagnose_agent,
        attempts_csv=attempts_csv,
    )

    traj_str = " → ".join(str(e) for e in result.error_reduction_trajectory)
    outcome = "✓ COMPILED" if result.compile_success else f"✗ {result.status}"
    print(
        f"      {outcome} | attempts: {result.total_attempts} | "
        f"errors: {result.initial_error_count}→{result.final_error_count} | "
        f"trajectory: [{traj_str}]"
    )
    return result


# ---------------------------------------------------------------------------
# Results writer
# ---------------------------------------------------------------------------

def _append_jsonl(path: Path, record: RunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    # Apply config overrides.
    if args.provider:
        config.MODEL_PROVIDER = args.provider
    if args.model:
        config.MODEL_ID = args.model

    project_root = Path(__file__).parent
    datasets_root = project_root / "datasets-c"
    output_root = project_root / "output"
    experiments_root = project_root / "experiments"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiments_dir = experiments_root / timestamp
    experiments_dir.mkdir(parents=True, exist_ok=True)

    results_jsonl = experiments_dir / "results.jsonl"
    attempts_csv = experiments_dir / "attempts.csv"

    strategies_to_run: list[AprStrategyV2] = (
        [AprStrategyV2(s) for s in args.strategies]
        if args.strategies
        else list(AprStrategyV2)
    )

    # Save experiment config.
    config_data = {
        "timestamp": timestamp,
        "datasets": args.datasets,
        "strategies": [s.value for s in strategies_to_run],
        "max_attempts": args.max_attempts,
        "use_existing_translation": args.use_existing_translation,
        "model_provider": config.get_provider_name(),
        "model_id": config.get_model_id(),
    }
    (experiments_dir / "config.json").write_text(
        json.dumps(config_data, indent=2), encoding="utf-8"
    )

    print()
    print("=" * 70)
    print("APR v2 PILOT EXPERIMENT")
    print("=" * 70)
    print(f"Provider  : {config.get_provider_name()}")
    print(f"Model     : {config.get_model_id()}")
    print(f"Datasets  : {', '.join(args.datasets)}")
    print(f"Strategies: {', '.join(s.value for s in strategies_to_run)}")
    print(f"Max attempts per strategy: {args.max_attempts}")
    print(f"Output    : {experiments_dir}")
    print("=" * 70)

    # Create agents once — shared across all datasets and strategies.
    model = config.get_model()
    repair_agent, diagnose_agent = create_agents(model)

    all_results: list[RunResult] = []

    for dataset in args.datasets:
        print(f"\nDATASET: {dataset}")
        print("-" * 50)

        dataset_path = datasets_root / dataset
        if not dataset_path.exists():
            print(f"  [!] Dataset not found at {dataset_path}, skipping.")
            continue

        # --- Translation ---
        gate_passed, _ = _load_or_run_translation(
            dataset, datasets_root, output_root, args.use_existing_translation
        )

        translated_dir = output_root / f"{dataset}-rust"
        if not translated_dir.exists():
            print(f"  [!] No translated output at {translated_dir}, skipping.")
            continue

        if not gate_passed:
            print("  [!] Fidelity gate FAILED — skipping APR for this dataset.")
            # Still record skipped results so the JSONL is complete.
            for strategy in strategies_to_run:
                skipped = RunResult(
                    dataset_name=dataset,
                    strategy_name=strategy.value,
                    compile_success=False,
                    total_attempts=0,
                    error_reduction_trajectory=[],
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                    patch_size_loc=0,
                    initial_error_count=0,
                    final_error_count=0,
                    duration_seconds=0.0,
                    status="translation_gate_failed",
                    rejected_attempts=0,
                )
                all_results.append(skipped)
                _append_jsonl(results_jsonl, skipped)
            continue

        # --- APR strategies ---
        for strategy in strategies_to_run:
            try:
                result = _run_one_strategy(
                    strategy=strategy,
                    dataset=dataset,
                    translated_dir=translated_dir,
                    experiments_dir=experiments_dir,
                    max_attempts=args.max_attempts,
                    repair_agent=repair_agent,
                    diagnose_agent=diagnose_agent,
                    attempts_csv=attempts_csv,
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                import traceback
                print(f"      [!] Strategy {strategy.value} failed with exception: {exc}")
                traceback.print_exc()
                result = RunResult(
                    dataset_name=dataset,
                    strategy_name=strategy.value,
                    compile_success=False,
                    total_attempts=0,
                    error_reduction_trajectory=[],
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                    patch_size_loc=0,
                    initial_error_count=0,
                    final_error_count=0,
                    duration_seconds=0.0,
                    status=f"error: {exc}",
                    rejected_attempts=0,
                )

            all_results.append(result)
            _append_jsonl(results_jsonl, result)

    # --- Summary table ---
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"{'Dataset':<20} {'Strategy':<25} {'Success':<8} {'Attempts':<10} {'Errors':<14} {'Tokens'}")
    print("-" * 90)
    for r in all_results:
        success_str = "YES" if r.compile_success else "no"
        errors_str = f"{r.initial_error_count}→{r.final_error_count}"
        tokens_str = f"{r.total_prompt_tokens + r.total_completion_tokens:,}"
        print(
            f"{r.dataset_name:<20} {r.strategy_name:<25} {success_str:<8} "
            f"{r.total_attempts:<10} {errors_str:<14} {tokens_str}"
        )

    print()
    print(f"Results JSONL : {results_jsonl}")
    print(f"Attempts CSV  : {attempts_csv}")

    # --- Plots ---
    if all_results:
        plots_dir = experiments_dir / "plots"
        try:
            generate_plots(results_jsonl, attempts_csv, plots_dir)
            print(f"Plots         : {plots_dir}")
        except Exception as exc:
            print(f"[!] Plotting failed: {exc}")

    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        raise SystemExit(130)
