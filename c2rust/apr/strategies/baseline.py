"""Strategy 1 — Baseline: raw terminal compiler output → single LLM call.

The prompt contains only the raw terminal dump from rustc and the full target
Rust file.  No structured parsing, no C source, no memory — this is the
simplest possible prompting approach and serves as the lower-bound baseline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from c2rust.agents.apr_agent import get_token_usage, repair_target_file
from c2rust.apr.strategies.base import CargoJsonError, MemoryEntry, StrategyRunResult

# Cap raw output to keep prompts within model context limits.
_RAW_OUTPUT_MAX_CHARS = 8_000


def build_prompt(
    rendered_output: str,
    rust_code: str,
    rust_file_path: Path,
) -> str:
    """Build the baseline prompt: raw terminal dump + full Rust file."""
    lines: list[str] = [
        "Fix the Rust file below to eliminate the compiler errors.",
        "Return ONLY the complete updated Rust file content.",
        "Do not output markdown fences, explanations, or any text other than the Rust source.",
        "",
        "## Raw Compiler Output",
        "```",
        rendered_output[:_RAW_OUTPUT_MAX_CHARS],
        "```",
        "",
        f"## Target Rust File: {rust_file_path.name}",
        "```rust",
        rust_code,
        "```",
    ]
    return "\n".join(lines)


def run(
    repair_agent: Any,
    diagnose_agent: Any,           # unused — kept for uniform signature
    rendered_output: str,
    json_errors: list[CargoJsonError],
    rust_code: str,
    rust_file_path: Path,
    memory_entries: list[MemoryEntry] | None = None,  # unused
) -> StrategyRunResult:
    """Execute one repair attempt."""
    prompt = build_prompt(rendered_output, rust_code, rust_file_path)
    patched, response = repair_target_file(repair_agent, prompt)
    pt, ct = get_token_usage(response)
    return StrategyRunResult(
        patched_code=patched,
        prompt_tokens=pt,
        completion_tokens=ct,
        diagnosis="",
        prompts=[prompt],
    )
