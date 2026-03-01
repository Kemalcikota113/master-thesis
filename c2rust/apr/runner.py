"""APR experiment runner with strategy-based context policies."""

import csv
import difflib
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from c2rust import config
from c2rust.agents.apr_agent import create_apr_agent, get_token_usage, repair_target_file
from c2rust.apr.context import AprStrategy, build_apr_prompt
from c2rust.pipeline.single_pass import run_single_pass
from c2rust.utils.fidelity import analyze_rust_output_quality, extract_rust_functions
from c2rust.utils.validation import ValidationResult, run_cargo_check


RUN_COLUMNS = [
    "timestamp",
    "dataset",
    "strategy",
    "translation_gate_passed",
    "translation_compile_success",
    "apr_started",
    "raw_translation_error_count",
    "apr_start_error_count",
    "compile_success",
    "status",
    "attempts_used",
    "max_attempts",
    "initial_error_count",
    "final_error_count",
    "error_reduction",
    "rejected_attempts",
    "tokens_prompt",
    "tokens_completion",
    "tokens_total",
    "duration_seconds",
    "translation_output_dir",
    "apr_project_dir",
]


SUMMARY_COLUMNS = [
    "dataset",
    "strategy",
    "status",
    "compile_success",
    "attempts_used",
    "initial_error_count",
    "final_error_count",
    "error_reduction",
    "rejected_attempts",
    "tokens_total",
    "duration_seconds",
]


ATTEMPT_COLUMNS = [
    "timestamp",
    "dataset",
    "strategy",
    "attempt",
    "error_code",
    "error_category",
    "error_file",
    "error_line",
    "error_message",
    "target_rust_file",
    "source_file_included",
    "source_file",
    "related_files_count",
    "errors_before",
    "errors_after",
    "error_delta",
    "attempt_status",
    "guardrail_reason",
    "loc_before",
    "loc_after",
    "function_count_before",
    "function_count_after",
    "patch_changed_lines",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "duration_seconds",
    "compile_success_after",
]


@dataclass
class RunSummary:
    timestamp: str
    dataset: str
    strategy: str
    translation_gate_passed: bool
    translation_compile_success: bool
    apr_started: bool
    raw_translation_error_count: int
    apr_start_error_count: int
    compile_success: bool
    status: str
    attempts_used: int
    max_attempts: int
    initial_error_count: int
    final_error_count: int
    error_reduction: int
    rejected_attempts: int
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    duration_seconds: float
    translation_output_dir: str
    apr_project_dir: str


def _slug(dataset: str) -> str:
    return dataset.replace("/", "__")


def _write_csv_row(path: Path, columns: list[str], row: dict[str, object]):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _changed_lines(old_text: str, new_text: str) -> int:
    diff = difflib.ndiff(old_text.splitlines(), new_text.splitlines())
    changed = 0
    for line in diff:
        if line.startswith("+ ") or line.startswith("- "):
            changed += 1
    return changed


def _loc_count(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def _function_count(text: str) -> int:
    tmp_path = Path("/tmp/c2rust_apr_tmp.rs")
    tmp_path.write_text(text, encoding="utf-8")
    try:
        return len(extract_rust_functions([tmp_path]))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _guardrail_check(
    new_text: str,
    baseline_loc: int,
    baseline_fn_count: int,
    min_loc_ratio: float = 0.7,
    min_fn_ratio: float = 0.8,
) -> tuple[bool, str, int, int]:
    loc_after = _loc_count(new_text)
    fn_after = _function_count(new_text)

    if baseline_loc > 0 and loc_after < int(baseline_loc * min_loc_ratio):
        return False, "loc_shrink_guardrail", loc_after, fn_after

    if baseline_fn_count > 0 and fn_after < int(baseline_fn_count * min_fn_ratio):
        return False, "function_drop_guardrail", loc_after, fn_after

    placeholders, truncation = analyze_rust_output_quality(new_text)
    if placeholders:
        return False, "placeholder_guardrail", loc_after, fn_after
    if truncation:
        return False, "truncation_guardrail", loc_after, fn_after

    return True, "", loc_after, fn_after


def _copy_project(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def _artifact_dir(experiments_dir: Path, dataset: str, strategy: str, attempt: int) -> Path:
    return experiments_dir / "artifacts" / _slug(dataset) / strategy / f"attempt_{attempt:02d}"


def _first_actionable_error(validation: ValidationResult, project_dir: Path):
    for error in validation.errors:
        if error.file == "unknown":
            continue
        path = project_dir / error.file
        if path.exists() and path.is_file():
            return error, path
    return None, None


def _error_signature(error) -> str:
    """Create stable error signature for stuck detection."""
    msg = (error.message or "").strip().lower()
    msg = re.sub(r"\d+", "N", msg)
    msg = re.sub(r"\s+", " ", msg)
    prefix = msg[:120]
    return f"{error.code}|{error.category.value}|{prefix}"


def _error_priority_score(error) -> tuple[int, int]:
    """Lower score is higher priority. Targets structural root causes first."""
    msg = (error.message or "").lower()

    # Root-cause classes first.
    if "cannot find macro" in msg:
        return (0, error.line)
    if "variadic" in msg or "valist" in msg or "c_variadic" in msg:
        return (1, error.line)
    if "cannot find function" in msg or "cannot find value" in msg or "unresolved" in msg:
        return (2, error.line)
    if "expected" in msg or "syntax" in msg:
        return (3, error.line)
    if error.category.value == "type":
        return (4, error.line)
    return (5, error.line)


def _select_actionable_error(validation: ValidationResult, project_dir: Path, recent_signatures: list[str]):
    """Select actionable error using priority and stuck-awareness."""
    candidates = []
    for error in validation.errors:
        if error.file == "unknown":
            continue
        path = project_dir / error.file
        if path.exists() and path.is_file():
            candidates.append((error, path))

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: _error_priority_score(item[0]))

    if len(recent_signatures) >= 2 and recent_signatures[-1] == recent_signatures[-2]:
        stuck_sig = recent_signatures[-1]
        for error, path in candidates:
            if _error_signature(error) != stuck_sig:
                return error, path

    return candidates[0]


def _hoist_macro_rules(text: str) -> str:
    """Move macro_rules blocks near top to reduce forward-reference errors."""
    macro_re = re.compile(r"(?ms)^macro_rules!\s+\w+\s*\{.*?^\}\s*$")
    blocks = macro_re.findall(text)
    if not blocks:
        return text

    stripped = macro_re.sub("", text).strip()
    lines = stripped.splitlines()
    insertion_index = 0
    for i, line in enumerate(lines):
        if line.startswith("use ") or line.startswith("const ") or line.startswith("type "):
            insertion_index = i + 1
            continue
        break

    prefix = "\n".join(lines[:insertion_index]).strip()
    suffix = "\n".join(lines[insertion_index:]).strip()
    macros = "\n\n".join(blocks).strip()

    rebuilt = []
    if prefix:
        rebuilt.append(prefix)
    if macros:
        rebuilt.append(macros)
    if suffix:
        rebuilt.append(suffix)
    return "\n\n".join(rebuilt).strip() + "\n"


def _run_strategy(
    dataset: str,
    dataset_path: Path,
    strategy: AprStrategy,
    translated_project_dir: Path,
    strategy_project_dir: Path,
    experiments_dir: Path,
    max_attempts: int,
    apr_agent,
    runs_csv: Path,
    summary_csv: Path,
    attempts_csv: Path,
    translation_gate_passed: bool,
    translation_compile_success: bool,
    apply_prepass: bool,
):
    started_at = time.time()
    ts = datetime.now().isoformat()

    _copy_project(translated_project_dir, strategy_project_dir)

    validation_raw = run_cargo_check(strategy_project_dir)
    raw_translation_error_count = len(validation_raw.errors)

    # Optional deterministic pre-pass to reduce forward-use macro errors.
    translated_dir = strategy_project_dir / "src" / "translated"
    if apply_prepass:
        for p in translated_dir.glob("*.rs"):
            original = p.read_text(encoding="utf-8", errors="ignore")
            updated = _hoist_macro_rules(original)
            if updated != original:
                p.write_text(updated, encoding="utf-8")
        validation = run_cargo_check(strategy_project_dir)
    else:
        validation = validation_raw

    apr_start_error_count = len(validation.errors)
    initial_error_count = apr_start_error_count

    if not translation_gate_passed:
        summary = RunSummary(
            timestamp=ts,
            dataset=dataset,
            strategy=strategy.value,
            translation_gate_passed=False,
            translation_compile_success=translation_compile_success,
            apr_started=False,
            raw_translation_error_count=raw_translation_error_count,
            apr_start_error_count=apr_start_error_count,
            compile_success=False,
            status="translation_gate_failed",
            attempts_used=0,
            max_attempts=max_attempts,
            initial_error_count=initial_error_count,
            final_error_count=initial_error_count,
            error_reduction=0,
            rejected_attempts=0,
            tokens_prompt=0,
            tokens_completion=0,
            tokens_total=0,
            duration_seconds=time.time() - started_at,
            translation_output_dir=str(translated_project_dir),
            apr_project_dir=str(strategy_project_dir),
        )
        _write_csv_row(runs_csv, RUN_COLUMNS, asdict(summary))
        _write_csv_row(
            summary_csv,
            SUMMARY_COLUMNS,
            {
                "dataset": summary.dataset,
                "strategy": summary.strategy,
                "status": summary.status,
                "compile_success": summary.compile_success,
                "attempts_used": summary.attempts_used,
                "initial_error_count": summary.initial_error_count,
                "final_error_count": summary.final_error_count,
                "error_reduction": summary.error_reduction,
                "rejected_attempts": summary.rejected_attempts,
                "tokens_total": summary.tokens_total,
                "duration_seconds": summary.duration_seconds,
            },
        )
        return

    if validation.success:
        summary = RunSummary(
            timestamp=ts,
            dataset=dataset,
            strategy=strategy.value,
            translation_gate_passed=True,
            translation_compile_success=translation_compile_success,
            apr_started=True,
            raw_translation_error_count=raw_translation_error_count,
            apr_start_error_count=apr_start_error_count,
            compile_success=True,
            status="already_compiles",
            attempts_used=0,
            max_attempts=max_attempts,
            initial_error_count=0,
            final_error_count=0,
            error_reduction=0,
            rejected_attempts=0,
            tokens_prompt=0,
            tokens_completion=0,
            tokens_total=0,
            duration_seconds=time.time() - started_at,
            translation_output_dir=str(translated_project_dir),
            apr_project_dir=str(strategy_project_dir),
        )
        _write_csv_row(runs_csv, RUN_COLUMNS, asdict(summary))
        _write_csv_row(
            summary_csv,
            SUMMARY_COLUMNS,
            {
                "dataset": summary.dataset,
                "strategy": summary.strategy,
                "status": summary.status,
                "compile_success": summary.compile_success,
                "attempts_used": summary.attempts_used,
                "initial_error_count": summary.initial_error_count,
                "final_error_count": summary.final_error_count,
                "error_reduction": summary.error_reduction,
                "rejected_attempts": summary.rejected_attempts,
                "tokens_total": summary.tokens_total,
                "duration_seconds": summary.duration_seconds,
            },
        )
        return

    total_prompt_tokens = 0
    total_completion_tokens = 0
    attempts_used = 0
    rejected_attempts = 0
    status = "apr_exhausted"
    recent_signatures: list[str] = []
    attempt_memory: list[str] = []

    # Baseline integrity measurements for anti-collapse guardrails.
    baseline_file_stats: dict[str, tuple[int, int]] = {}
    for p in translated_dir.glob("*.rs"):
        content = p.read_text(encoding="utf-8", errors="ignore")
        baseline_file_stats[str(p.relative_to(strategy_project_dir))] = (
            _loc_count(content),
            _function_count(content),
        )

    # Baseline row (attempt 0) for line plots.
    _write_csv_row(
        attempts_csv,
        ATTEMPT_COLUMNS,
        {
            "timestamp": ts,
            "dataset": dataset,
            "strategy": strategy.value,
            "attempt": 0,
            "error_code": "",
            "error_category": "",
            "error_file": "",
            "error_line": 0,
            "error_message": "baseline",
            "target_rust_file": "",
            "source_file_included": False,
            "source_file": "",
            "related_files_count": 0,
            "errors_before": apr_start_error_count,
            "errors_after": apr_start_error_count,
            "error_delta": 0,
            "attempt_status": "baseline",
            "guardrail_reason": "",
            "loc_before": 0,
            "loc_after": 0,
            "function_count_before": 0,
            "function_count_after": 0,
            "patch_changed_lines": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "duration_seconds": 0.0,
            "compile_success_after": validation.success,
        },
    )

    for attempt in range(1, max_attempts + 1):
        attempt_started = time.time()
        attempts_used = attempt

        error, target_file = _select_actionable_error(validation, strategy_project_dir, recent_signatures)
        if error is None or target_file is None:
            status = "no_actionable_error"
            break

        current_sig = _error_signature(error)
        recent_signatures.append(current_sig)

        before_errors = len(validation.errors)
        old_content = target_file.read_text(encoding="utf-8", errors="ignore")
        relative_target = str(target_file.relative_to(strategy_project_dir))
        baseline_loc, baseline_fn_count = baseline_file_stats.get(
            relative_target,
            (_loc_count(old_content), _function_count(old_content)),
        )

        prompt, ctx_meta = build_apr_prompt(
            strategy=strategy,
            error=error,
            raw_compile_output=validation.raw_output,
            failing_rust_file=target_file,
            dataset_path=dataset_path,
            project_dir=strategy_project_dir,
            attempt_memory=attempt_memory,
        )

        updated_content, response = repair_target_file(apr_agent, prompt)
        prompt_tokens, completion_tokens = get_token_usage(response)
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens

        guard_ok, guard_reason, loc_after, fn_after = _guardrail_check(
            updated_content,
            baseline_loc=baseline_loc,
            baseline_fn_count=baseline_fn_count,
        )

        changed_lines = _changed_lines(old_content, updated_content)
        attempt_status = "applied"

        if guard_ok:
            target_file.write_text(updated_content + "\n", encoding="utf-8")
            validation_after = run_cargo_check(strategy_project_dir)
            after_errors = len(validation_after.errors)

            # Regression guard: revert if errors increase significantly.
            if after_errors > before_errors + 3:
                rejected_attempts += 1
                attempt_status = "reverted_regression"
                guard_reason = "regression_guardrail"
                target_file.write_text(old_content, encoding="utf-8")
                validation_after = validation
                after_errors = before_errors
                changed_lines = 0
        else:
            rejected_attempts += 1
            attempt_status = "rejected_guardrail"
            validation_after = validation
            after_errors = before_errors
            changed_lines = 0

        attempt_memory.append(
            f"Attempt {attempt}: sig={current_sig[:80]} status={attempt_status} "
            f"errors {before_errors}->{after_errors}"
        )

        art_dir = _artifact_dir(experiments_dir, dataset, strategy.value, attempt)
        art_dir.mkdir(parents=True, exist_ok=True)
        (art_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        (art_dir / "response.txt").write_text(updated_content, encoding="utf-8")
        (art_dir / "compile_output_before.txt").write_text(validation.raw_output, encoding="utf-8")
        (art_dir / "compile_output_after.txt").write_text(validation_after.raw_output, encoding="utf-8")
        (art_dir / "context_meta.json").write_text(json.dumps(ctx_meta, indent=2), encoding="utf-8")

        attempt_row = {
            "timestamp": ts,
            "dataset": dataset,
            "strategy": strategy.value,
            "attempt": attempt,
            "error_code": error.code,
            "error_category": error.category.value,
            "error_file": error.file,
            "error_line": error.line,
            "error_message": error.message,
            "target_rust_file": relative_target,
            "source_file_included": ctx_meta.get("source_file_included", False),
            "source_file": ctx_meta.get("source_file", ""),
            "related_files_count": ctx_meta.get("related_files_count", 0),
            "errors_before": before_errors,
            "errors_after": after_errors,
            "error_delta": before_errors - after_errors,
            "attempt_status": attempt_status,
            "guardrail_reason": guard_reason,
            "loc_before": baseline_loc,
            "loc_after": loc_after,
            "function_count_before": baseline_fn_count,
            "function_count_after": fn_after,
            "patch_changed_lines": changed_lines,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "duration_seconds": time.time() - attempt_started,
            "compile_success_after": validation_after.success,
        }
        _write_csv_row(attempts_csv, ATTEMPT_COLUMNS, attempt_row)

        validation = validation_after
        if validation.success:
            status = "compile_success"
            break

    summary = RunSummary(
        timestamp=ts,
        dataset=dataset,
        strategy=strategy.value,
        translation_gate_passed=True,
        translation_compile_success=translation_compile_success,
        apr_started=True,
        raw_translation_error_count=raw_translation_error_count,
        apr_start_error_count=apr_start_error_count,
        compile_success=validation.success,
        status=status,
        attempts_used=attempts_used,
        max_attempts=max_attempts,
        initial_error_count=initial_error_count,
        final_error_count=len(validation.errors),
        error_reduction=initial_error_count - len(validation.errors),
        rejected_attempts=rejected_attempts,
        tokens_prompt=total_prompt_tokens,
        tokens_completion=total_completion_tokens,
        tokens_total=total_prompt_tokens + total_completion_tokens,
        duration_seconds=time.time() - started_at,
        translation_output_dir=str(translated_project_dir),
        apr_project_dir=str(strategy_project_dir),
    )
    _write_csv_row(runs_csv, RUN_COLUMNS, asdict(summary))
    _write_csv_row(
        summary_csv,
        SUMMARY_COLUMNS,
        {
            "dataset": summary.dataset,
            "strategy": summary.strategy,
            "status": summary.status,
            "compile_success": summary.compile_success,
            "attempts_used": summary.attempts_used,
            "initial_error_count": summary.initial_error_count,
            "final_error_count": summary.final_error_count,
            "error_reduction": summary.error_reduction,
            "rejected_attempts": summary.rejected_attempts,
            "tokens_total": summary.tokens_total,
            "duration_seconds": summary.duration_seconds,
        },
    )


def run_apr_experiment(
    datasets: list[str],
    datasets_root: Path,
    output_root: Path,
    experiments_root: Path,
    max_attempts: int = 5,
    use_existing_translation: bool = False,
    apply_prepass: bool = False,
):
    """Run translation + APR context strategy experiment for datasets."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiments_dir = experiments_root / timestamp
    experiments_dir.mkdir(parents=True, exist_ok=True)

    runs_csv = experiments_dir / "runs.csv"
    summary_csv = experiments_dir / "summary.csv"
    attempts_csv = experiments_dir / "attempts.csv"

    config_path = experiments_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "datasets": datasets,
                "strategies": [s.value for s in AprStrategy],
                "max_attempts": max_attempts,
                "use_existing_translation": use_existing_translation,
                "apply_prepass": apply_prepass,
                "model_provider": config.get_provider_name(),
                "model_id": config.get_model_id(),
                "translation_stage": "single_pass_with_fidelity_gate",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    model = config.get_model()
    apr_agent = create_apr_agent(model)

    for dataset in datasets:
        print("\n" + "=" * 70)
        print(f"DATASET: {dataset}")
        print("=" * 70)
        dataset_path = datasets_root / dataset
        if not dataset_path.exists():
            print(f"Dataset not found, skipping: {dataset_path}")
            continue

        translated_project_dir = output_root / f"{dataset}-rust"
        if use_existing_translation:
            print("Using existing translation artifacts...")
            metrics_path = translated_project_dir / "metrics.json"
            if not metrics_path.exists():
                print(f"Missing existing metrics file: {metrics_path}")
                continue
            t_data = json.loads(metrics_path.read_text(encoding="utf-8"))

            class _Metrics:
                fidelity_gate_passed = bool(t_data.get("fidelity_gate_passed", False))
                compile_success = bool(t_data.get("compile_success", False))

            t_metrics = _Metrics()
        else:
            print("Running translation stage...")
            t_metrics = run_single_pass(dataset, datasets_root, output_root)

        for strategy in AprStrategy:
            print(f"\nAPR strategy: {strategy.value}")
            strategy_project_dir = (
                experiments_dir
                / "projects"
                / _slug(dataset)
                / strategy.value
                / "project"
            )

            _run_strategy(
                dataset=dataset,
                dataset_path=dataset_path,
                strategy=strategy,
                translated_project_dir=translated_project_dir,
                strategy_project_dir=strategy_project_dir,
                experiments_dir=experiments_dir,
                max_attempts=max_attempts,
                apr_agent=apr_agent,
                runs_csv=runs_csv,
                summary_csv=summary_csv,
                attempts_csv=attempts_csv,
                translation_gate_passed=t_metrics.fidelity_gate_passed,
                translation_compile_success=t_metrics.compile_success,
                apply_prepass=apply_prepass,
            )

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)
    print(f"Results: {experiments_dir}")
    print(f"Runs CSV: {runs_csv}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Attempts CSV: {attempts_csv}")
