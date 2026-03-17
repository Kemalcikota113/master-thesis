"""APR v2 runner: iterative compile-error repair loop for the four new strategies.

Each call to `run_strategy_v2()` operates on an already-isolated copy of the
translated Rust project.  The caller (run_pilot.py) is responsible for creating
one isolated copy per strategy before calling this function.

Loop invariant
--------------
At the start of every attempt:
  - `validation` holds the current compile state (from run_cargo_check_json).
  - `json_errors` is the structured error list for the current state.
  - `memory_entries` accumulates attempt outcomes (used only by S4; harmless for others).

Guardrails (applied before writing any patch)
---------------------------------------------
  - loc_shrink   : patched LOC < 70 % of baseline → reject
  - fn_drop      : patched function count < 80 % of baseline → reject
  - placeholder  : LLM introduced TODO / unimplemented! / panic!("TODO") → reject
  - truncation   : unbalanced braces or abrupt file ending → reject
  - regression   : error count increased by > 3 after write → revert
"""

from __future__ import annotations

import csv
import difflib
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from c2rust.agents.apr_agent import create_apr_agent, create_diagnose_agent
from c2rust.apr.strategies import (
    AprStrategyV2,
    CargoJsonError,
    MemoryEntry,
    StrategyRunResult,
    STRATEGY_MODULES,
    run_cargo_check_json,
)
from c2rust.apr.strategies.memory_reflexion import make_memory_entry
from c2rust.utils.fidelity import analyze_rust_output_quality, extract_rust_functions
from c2rust.utils.validation import ValidationResult


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """Primary metrics record for one (dataset, strategy) run.

    One of these is written as a JSON line to results.jsonl.
    """

    dataset_name: str
    strategy_name: str
    compile_success: bool
    total_attempts: int
    error_reduction_trajectory: list[int]   # [initial, after_1, after_2, …]
    total_prompt_tokens: int
    total_completion_tokens: int
    patch_size_loc: int                     # cumulative changed lines (accepted patches only)
    initial_error_count: int
    final_error_count: int
    duration_seconds: float
    status: str                             # compile_success | apr_exhausted | no_actionable_error | already_compiles
    rejected_attempts: int


# Per-attempt detail columns (written to attempts.csv)
_ATTEMPT_COLUMNS = [
    "timestamp",
    "dataset",
    "strategy",
    "attempt",
    "error_code",
    "error_file",
    "error_line",
    "error_message",
    "target_rust_file",
    "errors_before",
    "errors_after",
    "error_delta",
    "attempt_status",          # applied | reverted_regression | rejected_guardrail
    "guardrail_reason",
    "loc_before",
    "loc_after",
    "function_count_before",
    "function_count_after",
    "patch_changed_lines",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "llm_calls",               # 1 for S1/S2, 2 for S3/S4
    "has_diagnosis",
    "duration_seconds",
    "compile_success_after",
]


# ---------------------------------------------------------------------------
# Small helpers (mirror runner.py; kept local to avoid cross-module coupling)
# ---------------------------------------------------------------------------

def _loc_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def _function_count(text: str) -> int:
    tmp = Path("/tmp/c2rust_runner_v2_tmp.rs")
    tmp.write_text(text, encoding="utf-8")
    try:
        return len(extract_rust_functions([tmp]))
    finally:
        if tmp.exists():
            tmp.unlink()


def _changed_lines(old: str, new: str) -> int:
    diff = difflib.ndiff(old.splitlines(), new.splitlines())
    return sum(1 for ln in diff if ln.startswith("+ ") or ln.startswith("- "))


def _guardrail_check(
    new_text: str,
    baseline_loc: int,
    baseline_fn_count: int,
    min_loc_ratio: float = 0.7,
    min_fn_ratio: float = 0.8,
) -> tuple[bool, str, int, int]:
    """Return (passes, reason, loc_after, fn_after)."""
    loc_after = _loc_count(new_text)
    fn_after = _function_count(new_text)

    if baseline_loc > 0 and loc_after < int(baseline_loc * min_loc_ratio):
        return False, "loc_shrink_guardrail", loc_after, fn_after
    if baseline_fn_count > 0 and fn_after < int(baseline_fn_count * min_fn_ratio):
        return False, "function_drop_guardrail", loc_after, fn_after

    placeholder_hits, truncation_reasons = analyze_rust_output_quality(new_text)
    if placeholder_hits:
        return False, "placeholder_guardrail", loc_after, fn_after
    if truncation_reasons:
        return False, "truncation_guardrail", loc_after, fn_after

    return True, "", loc_after, fn_after


def _error_priority_score(error: Any) -> tuple[int, int]:
    """Lower score = higher priority.  Targets structural root causes first."""
    msg = (error.message or "").lower()
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


def _error_signature(error: Any) -> str:
    msg = re.sub(r"\d+", "N", (error.message or "").strip().lower())
    msg = re.sub(r"\s+", " ", msg)
    return f"{error.code}|{error.category.value}|{msg[:120]}"


def _select_actionable_error(
    validation: ValidationResult,
    project_dir: Path,
    recent_signatures: list[str],
) -> tuple[Any | None, Path | None]:
    """Pick the highest-priority, file-resolvable error; skip stuck signatures."""
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

    # If last two attempts hit the same signature, try a different error first.
    if len(recent_signatures) >= 2 and recent_signatures[-1] == recent_signatures[-2]:
        stuck_sig = recent_signatures[-1]
        for error, path in candidates:
            if _error_signature(error) != stuck_sig:
                return error, path

    return candidates[0]


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    return name.replace("/", "__")


def _artifact_dir(experiments_dir: Path, dataset: str, strategy: str, attempt: int) -> Path:
    return experiments_dir / "artifacts" / _slug(dataset) / strategy / f"attempt_{attempt:02d}"


def _write_csv_row(path: Path, columns: list[str], row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _save_artifacts(
    art_dir: Path,
    result: StrategyRunResult,
    compile_before: str,
    compile_after: str,
) -> None:
    art_dir.mkdir(parents=True, exist_ok=True)
    for i, prompt in enumerate(result.prompts, start=1):
        label = "prompt" if len(result.prompts) == 1 else f"prompt_{i:02d}"
        (art_dir / f"{label}.txt").write_text(prompt, encoding="utf-8")
    if result.diagnosis:
        (art_dir / "diagnosis.txt").write_text(result.diagnosis, encoding="utf-8")
    (art_dir / "response.txt").write_text(result.patched_code, encoding="utf-8")
    (art_dir / "compile_before.txt").write_text(compile_before, encoding="utf-8")
    (art_dir / "compile_after.txt").write_text(compile_after, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main per-strategy loop
# ---------------------------------------------------------------------------

def run_strategy_v2(
    strategy: AprStrategyV2,
    dataset: str,
    project_dir: Path,
    experiments_dir: Path,
    max_attempts: int,
    repair_agent: Any,
    diagnose_agent: Any,
    attempts_csv: Path,
) -> RunResult:
    """Run the iterative APR loop for one strategy on an isolated project copy.

    Args:
        strategy        : which strategy to run
        dataset         : dataset name (for logging)
        project_dir     : isolated Rust project directory (already a copy of the baseline)
        experiments_dir : root experiments directory (for artifacts)
        max_attempts    : maximum repair iterations
        repair_agent    : agno Agent for code output (all strategies)
        diagnose_agent  : agno Agent for analysis text (S3/S4 only)
        attempts_csv    : path to the shared per-attempt CSV

    Returns:
        RunResult with all metrics for this (dataset, strategy) pair.
    """
    started_at = time.time()
    ts = datetime.now().isoformat()
    strategy_module = STRATEGY_MODULES[strategy]
    translated_dir = project_dir / "src" / "translated"

    # ------------------------------------------------------------------
    # Initial compile
    # ------------------------------------------------------------------
    validation, json_errors = run_cargo_check_json(project_dir)
    initial_error_count = len(validation.errors)
    trajectory: list[int] = [initial_error_count]

    # ------------------------------------------------------------------
    # Early-exit: already compiles
    # ------------------------------------------------------------------
    if validation.success:
        return RunResult(
            dataset_name=dataset,
            strategy_name=strategy.value,
            compile_success=True,
            total_attempts=0,
            error_reduction_trajectory=trajectory,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            patch_size_loc=0,
            initial_error_count=0,
            final_error_count=0,
            duration_seconds=time.time() - started_at,
            status="already_compiles",
            rejected_attempts=0,
        )

    # ------------------------------------------------------------------
    # Baseline measurements for guardrails
    # ------------------------------------------------------------------
    baseline_file_stats: dict[str, tuple[int, int]] = {}
    for rs_file in translated_dir.glob("*.rs"):
        content = rs_file.read_text(encoding="utf-8", errors="ignore")
        rel = str(rs_file.relative_to(project_dir))
        baseline_file_stats[rel] = (_loc_count(content), _function_count(content))

    # ------------------------------------------------------------------
    # Baseline row (attempt 0) in the per-attempt CSV
    # ------------------------------------------------------------------
    _write_csv_row(
        attempts_csv,
        _ATTEMPT_COLUMNS,
        {
            "timestamp": ts, "dataset": dataset, "strategy": strategy.value,
            "attempt": 0, "error_code": "", "error_file": "", "error_line": 0,
            "error_message": "baseline", "target_rust_file": "",
            "errors_before": initial_error_count, "errors_after": initial_error_count,
            "error_delta": 0, "attempt_status": "baseline", "guardrail_reason": "",
            "loc_before": 0, "loc_after": 0,
            "function_count_before": 0, "function_count_after": 0,
            "patch_changed_lines": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "llm_calls": 0, "has_diagnosis": False,
            "duration_seconds": 0.0, "compile_success_after": False,
        },
    )

    # ------------------------------------------------------------------
    # Repair loop
    # ------------------------------------------------------------------
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_patch_loc = 0
    rejected_attempts = 0
    recent_signatures: list[str] = []
    memory_entries: list[MemoryEntry] = []
    status = "apr_exhausted"

    for attempt in range(1, max_attempts + 1):
        attempt_started = time.time()

        # Select which file/error to target this iteration.
        error, target_file = _select_actionable_error(
            validation, project_dir, recent_signatures
        )
        if error is None or target_file is None:
            status = "no_actionable_error"
            break

        current_sig = _error_signature(error)
        recent_signatures.append(current_sig)

        errors_before = len(validation.errors)
        old_content = target_file.read_text(encoding="utf-8", errors="ignore")
        rel_target = str(target_file.relative_to(project_dir))
        baseline_loc, baseline_fn = baseline_file_stats.get(
            rel_target,
            (_loc_count(old_content), _function_count(old_content)),
        )

        # Find the CargoJsonError that matches the selected ValidationError so
        # strategies receive a typed object (not just the plain ValidationError).
        matching_json = next(
            (e for e in json_errors if e.file == error.file and e.line_start == error.line),
            None,
        )
        # Fallback: synthesise a CargoJsonError from the ValidationError fields.
        if matching_json is None:
            matching_json = CargoJsonError(
                code=error.code,
                message=error.message,
                file=error.file,
                line_start=error.line,
                col_start=error.column,
                label="",
                suggested_replacement=None,
                rendered=error.raw,
            )

        # ------------------------------------------------------------------
        # Call the strategy
        # ------------------------------------------------------------------
        result: StrategyRunResult = strategy_module.run(
            repair_agent=repair_agent,
            diagnose_agent=diagnose_agent,
            rendered_output=validation.raw_output,
            json_errors=json_errors,
            rust_code=old_content,
            rust_file_path=target_file,
            memory_entries=memory_entries,
        )

        total_prompt_tokens += result.prompt_tokens
        total_completion_tokens += result.completion_tokens

        # ------------------------------------------------------------------
        # Guardrail check
        # ------------------------------------------------------------------
        guard_ok, guard_reason, loc_after, fn_after = _guardrail_check(
            result.patched_code, baseline_loc, baseline_fn
        )
        changed_lines = _changed_lines(old_content, result.patched_code)
        attempt_status = "applied"

        if guard_ok:
            target_file.write_text(result.patched_code + "\n", encoding="utf-8")
            validation_after, json_errors_after = run_cargo_check_json(project_dir)
            errors_after = len(validation_after.errors)

            # Regression guard: revert if errors increase significantly.
            if errors_after > errors_before + 3:
                rejected_attempts += 1
                attempt_status = "reverted_regression"
                guard_reason = "regression_guardrail"
                target_file.write_text(old_content, encoding="utf-8")
                validation_after, json_errors_after = validation, json_errors
                errors_after = errors_before
                changed_lines = 0
            else:
                total_patch_loc += changed_lines
        else:
            rejected_attempts += 1
            attempt_status = "rejected_guardrail"
            validation_after, json_errors_after = validation, json_errors
            errors_after = errors_before
            changed_lines = 0

        # ------------------------------------------------------------------
        # Save artifacts
        # ------------------------------------------------------------------
        art_dir = _artifact_dir(experiments_dir, dataset, strategy.value, attempt)
        _save_artifacts(art_dir, result, validation.raw_output, validation_after.raw_output)

        # ------------------------------------------------------------------
        # Log per-attempt row
        # ------------------------------------------------------------------
        _write_csv_row(
            attempts_csv,
            _ATTEMPT_COLUMNS,
            {
                "timestamp": ts,
                "dataset": dataset,
                "strategy": strategy.value,
                "attempt": attempt,
                "error_code": error.code,
                "error_file": error.file,
                "error_line": error.line,
                "error_message": error.message,
                "target_rust_file": rel_target,
                "errors_before": errors_before,
                "errors_after": errors_after,
                "error_delta": errors_before - errors_after,
                "attempt_status": attempt_status,
                "guardrail_reason": guard_reason,
                "loc_before": baseline_loc,
                "loc_after": loc_after,
                "function_count_before": baseline_fn,
                "function_count_after": fn_after,
                "patch_changed_lines": changed_lines,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.prompt_tokens + result.completion_tokens,
                "llm_calls": len(result.prompts),
                "has_diagnosis": bool(result.diagnosis),
                "duration_seconds": round(time.time() - attempt_started, 2),
                "compile_success_after": validation_after.success,
            },
        )

        # ------------------------------------------------------------------
        # Build memory entry (runner always maintains it; only S4 uses it)
        # ------------------------------------------------------------------
        memory_entries.append(
            make_memory_entry(
                attempt=attempt,
                targeted_error=matching_json,
                diagnosis=result.diagnosis,
                errors_before=errors_before,
                errors_after=errors_after,
                status=attempt_status,
            )
        )

        # Advance state.
        trajectory.append(errors_after)
        validation = validation_after
        json_errors = json_errors_after

        if validation.success:
            status = "compile_success"
            break

    return RunResult(
        dataset_name=dataset,
        strategy_name=strategy.value,
        compile_success=validation.success,
        total_attempts=len(trajectory) - 1,   # trajectory[0] is the baseline
        error_reduction_trajectory=trajectory,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        patch_size_loc=total_patch_loc,
        initial_error_count=initial_error_count,
        final_error_count=len(validation.errors),
        duration_seconds=round(time.time() - started_at, 2),
        status=status,
        rejected_attempts=rejected_attempts,
    )


# ---------------------------------------------------------------------------
# Agent factory (convenience — used by run_pilot.py)
# ---------------------------------------------------------------------------

def create_agents(model: Any) -> tuple[Any, Any]:
    """Return (repair_agent, diagnose_agent) from a single model instance."""
    return create_apr_agent(model), create_diagnose_agent(model)
