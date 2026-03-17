"""Strategy 2 — Structured Compiler: cargo JSON errors → structured prompt → LLM.

The key upgrade over Baseline: instead of dumping raw terminal text, the errors
are parsed from `cargo check --message-format=json` and formatted as a numbered
list containing the exact error code, file:line:col, message, span label, and
any compiler-suggested replacement.  This gives the LLM precise, noise-free
signal for each error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from c2rust.agents.apr_agent import get_token_usage, repair_target_file
from c2rust.apr.strategies.base import CargoJsonError, MemoryEntry, StrategyRunResult

_MAX_ERRORS_IN_PROMPT = 20


def format_error_list(errors: list[CargoJsonError], max_errors: int = _MAX_ERRORS_IN_PROMPT) -> str:
    """Format CargoJsonErrors as a readable, numbered list."""
    parts: list[str] = []
    shown = errors[:max_errors]
    for i, e in enumerate(shown, start=1):
        parts.append(f"{i}. [{e.code}] {e.file}:{e.line_start}:{e.col_start}")
        parts.append(f"   Message  : {e.message}")
        if e.label:
            parts.append(f"   Label    : {e.label}")
        if e.suggested_replacement:
            replacement = e.suggested_replacement.strip().replace("\n", "\\n")
            parts.append(f"   Suggested: {replacement[:120]}")
        parts.append("")
    if len(errors) > max_errors:
        parts.append(f"... and {len(errors) - max_errors} more errors (fix the above first).")
    return "\n".join(parts)


def build_prompt(
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
) -> str:
    """Build the structured compiler prompt."""
    error_count = len(json_errors)
    lines: list[str] = [
        "Fix the Rust file below to eliminate the compiler errors.",
        "Return ONLY the complete updated Rust file content.",
        "Do not output markdown fences, explanations, or any text other than the Rust source.",
        "",
        f"## Structured Compiler Errors ({error_count} total)",
        format_error_list(json_errors),
        f"## Target Rust File: {rust_file_path.name}",
        "```rust",
        rust_code,
        "```",
    ]
    return "\n".join(lines)


def run(
    repair_agent: Any,
    diagnose_agent: Any,           # unused — kept for uniform signature
    rendered_output: str,          # unused — kept for uniform signature
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
    memory_entries: list[MemoryEntry] | None = None,  # unused
) -> StrategyRunResult:
    """Execute one repair attempt using structured JSON compiler errors."""
    prompt = build_prompt(json_errors, rust_code, rust_file_path)
    patched, response = repair_target_file(repair_agent, prompt)
    pt, ct = get_token_usage(response)
    return StrategyRunResult(
        patched_code=patched,
        prompt_tokens=pt,
        completion_tokens=ct,
        diagnosis="",
        prompts=[prompt],
    )
