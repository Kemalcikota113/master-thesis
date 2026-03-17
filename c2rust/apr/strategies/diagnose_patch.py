"""Strategy 3 — Diagnose-then-Patch (Chain of Thought): 2 LLM calls per attempt.

Call 1 (diagnose): The LLM is asked to produce a structured root-cause analysis,
    list of target symbols, and an ordered fix plan.  It must NOT output any Rust code.

Call 2 (patch): The LLM receives the diagnosis from Call 1 plus the Rust file and
    is asked to output ONLY the patched Rust source.

Separating analysis from code generation reduces chaotic multi-error edits and
prevents the model from jumping straight to a local fix that misses the root cause.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from c2rust.agents.apr_agent import get_token_usage, repair_target_file
from c2rust.apr.strategies.base import CargoJsonError, MemoryEntry, StrategyRunResult
from c2rust.apr.strategies.structured import format_error_list

_MAX_ERRORS_DIAGNOSE = 20
_MAX_ERRORS_PATCH = 10    # Patch prompt is shorter to save tokens


def build_diagnose_prompt(
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
) -> str:
    """Call-1 prompt: request root-cause analysis and fix plan only (no code)."""
    lines: list[str] = [
        "You are a Rust compiler-error analyst. Analyse the errors and file below.",
        "Produce a structured diagnosis with EXACTLY these three sections:",
        "",
        "  1. ROOT CAUSE   — the underlying reason(s) the code does not compile",
        "  2. TARGET SYMBOLS — specific function names, types, macros, or variables to change",
        "  3. FIX PLAN     — ordered, concrete steps to resolve the errors",
        "",
        "IMPORTANT: Do NOT output any Rust code. Output analysis text only.",
        "",
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
) -> str:
    """Call-2 prompt: apply the fix plan and return only patched Rust code."""
    lines: list[str] = [
        "You are a Rust compiler-error repair assistant.",
        "Using the diagnosis below, fix the Rust file.",
        "Return ONLY the complete updated Rust file content.",
        "Do not output markdown fences, explanations, or any text other than the Rust source.",
        "",
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


def run(
    repair_agent: Any,
    diagnose_agent: Any,
    rendered_output: str,          # unused — kept for uniform signature
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
    memory_entries: list[MemoryEntry] | None = None,  # unused
) -> StrategyRunResult:
    """Execute one repair attempt with diagnose-then-patch CoT."""
    # --- Call 1: Diagnosis ---
    d_prompt = build_diagnose_prompt(json_errors, rust_code, rust_file_path)
    d_response = diagnose_agent.run(d_prompt)
    diagnosis = _extract_text(d_response)
    d_pt, d_ct = get_token_usage(d_response)

    # --- Call 2: Patch ---
    p_prompt = build_patch_prompt(diagnosis, json_errors, rust_code, rust_file_path)
    patched, p_response = repair_target_file(repair_agent, p_prompt)
    p_pt, p_ct = get_token_usage(p_response)

    return StrategyRunResult(
        patched_code=patched,
        prompt_tokens=d_pt + p_pt,
        completion_tokens=d_ct + p_ct,
        diagnosis=diagnosis,
        prompts=[d_prompt, p_prompt],
    )
