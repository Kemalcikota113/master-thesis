"""Strategy 4 — Memory/Reflexion: Diagnose-then-Patch augmented with attempt memory.

Builds directly on Strategy 3.  Before each Call-1 (diagnose) and Call-2 (patch),
a structured memory block is prepended that summarises every previous attempt in
the current run:

    Attempt N: targeted [E0425] "cannot find value …"
               errors 55 → 48 (↓7) | applied but errors remain
               Plan was: Remove the goto_cleanup! macro call and replace with …

This prevents the model from repeating the same failed fix pattern — the key
failure mode observed in the SDS pilot where macro-related errors caused a plateau.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from c2rust.agents.apr_agent import get_token_usage, repair_target_file
from c2rust.apr.strategies.base import CargoJsonError, MemoryEntry, StrategyRunResult
from c2rust.apr.strategies.structured import format_error_list

_MAX_ERRORS_DIAGNOSE = 20
_MAX_ERRORS_PATCH = 10


def format_memory_block(entries: list[MemoryEntry]) -> str:
    """Render previous attempt outcomes as a structured, readable block."""
    if not entries:
        return "(no previous attempts — this is the first attempt)"

    lines: list[str] = [
        "Previous attempts are summarised below.",
        "You MUST avoid repeating the same changes that failed.",
        "",
    ]
    for e in entries:
        delta = e.errors_before - e.errors_after
        if delta > 0:
            direction = f"↓{delta} errors fixed"
        elif delta < 0:
            direction = f"↑{abs(delta)} REGRESSION"
        else:
            direction = "↔ no change"

        if e.status == "reverted_regression":
            outcome = "REVERTED (error count increased — patch was harmful)"
        elif e.status == "rejected_guardrail":
            outcome = "REJECTED (guardrail: excessive code deletion or placeholders introduced)"
        else:
            outcome = "applied but compile still fails"

        lines.append(
            f"Attempt {e.attempt}: [{e.targeted_error_code}] "
            f'"{e.targeted_error_message[:80]}"'
        )
        lines.append(f"  Result  : {e.errors_before} → {e.errors_after} errors ({direction}) | {outcome}")
        if e.diagnosis_summary:
            for dline in e.diagnosis_summary.splitlines():
                lines.append(f"  {dline}")
        lines.append("")

    return "\n".join(lines)


def build_diagnose_prompt(
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
    memory_entries: list[MemoryEntry],
) -> str:
    """Call-1 prompt: root-cause analysis informed by attempt memory."""
    lines: list[str] = [
        "You are a Rust compiler-error analyst. Analyse the errors and file below.",
        "Produce a structured diagnosis with EXACTLY these three sections:",
        "",
        "  1. ROOT CAUSE   — the underlying reason(s) the code does not compile",
        "  2. TARGET SYMBOLS — specific function names, types, macros, or variables to change",
        "  3. FIX PLAN     — ordered, concrete steps to resolve the errors",
        "",
        "IMPORTANT: Do NOT output any Rust code. Output analysis text only.",
        "IMPORTANT: The memory block below shows what has already been tried and failed.",
        "           Your fix plan MUST differ from all previous failed approaches.",
        "",
        "## Attempt Memory",
        format_memory_block(memory_entries),
        f"## Compiler Errors ({len(json_errors)} total)",
        format_error_list(json_errors, max_errors=_MAX_ERRORS_DIAGNOSE),
        f"## Rust File: {rust_file_path.name}",
        "```rust",
        rust_code,
        "```",
    ]
    return "\n".join(lines)


def build_patch_prompt(
    diagnosis: str,
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
    memory_entries: list[MemoryEntry],
) -> str:
    """Call-2 prompt: apply the fix plan, guarded by memory of failures."""
    lines: list[str] = [
        "You are a Rust compiler-error repair assistant.",
        "Using the diagnosis and the memory of failed attempts, fix the Rust file.",
        "Return ONLY the complete updated Rust file content.",
        "Do not output markdown fences, explanations, or any text other than the Rust source.",
        "",
        "## Attempt Memory",
        format_memory_block(memory_entries),
        "## Diagnosis",
        diagnosis.strip(),
        "",
        f"## Compiler Errors ({len(json_errors)} total, for reference)",
        format_error_list(json_errors, max_errors=_MAX_ERRORS_PATCH),
        f"## Target Rust File: {rust_file_path.name}",
        "```rust",
        rust_code,
        "```",
    ]
    return "\n".join(lines)


def _extract_text(response: Any) -> str:
    if hasattr(response, "content"):
        return response.content or ""
    return str(response)


def make_memory_entry(
    attempt: int,
    targeted_error: CargoJsonError,
    diagnosis: str,
    errors_before: int,
    errors_after: int,
    status: str,
) -> MemoryEntry:
    """Construct a MemoryEntry from the results of one attempt."""
    return MemoryEntry(
        attempt=attempt,
        targeted_error_code=targeted_error.code,
        targeted_error_message=targeted_error.message,
        diagnosis_summary=diagnosis.strip(),
        errors_before=errors_before,
        errors_after=errors_after,
        status=status,
    )


def run(
    repair_agent: Any,
    diagnose_agent: Any,
    rendered_output: str,          # unused — kept for uniform signature
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
    memory_entries: list[MemoryEntry] | None = None,
) -> StrategyRunResult:
    """Execute one repair attempt with memory-augmented diagnose-then-patch."""
    entries = memory_entries or []

    # --- Call 1: Diagnosis with memory ---
    d_prompt = build_diagnose_prompt(json_errors, rust_code, rust_file_path, entries)
    d_response = diagnose_agent.run(d_prompt)
    diagnosis = _extract_text(d_response)
    d_pt, d_ct = get_token_usage(d_response)

    # --- Call 2: Patch with memory + diagnosis ---
    p_prompt = build_patch_prompt(diagnosis, json_errors, rust_code, rust_file_path, entries)
    patched, p_response = repair_target_file(repair_agent, p_prompt)
    p_pt, p_ct = get_token_usage(p_response)

    return StrategyRunResult(
        patched_code=patched,
        prompt_tokens=d_pt + p_pt,
        completion_tokens=d_ct + p_ct,
        diagnosis=diagnosis,
        prompts=[d_prompt, p_prompt],
    )
