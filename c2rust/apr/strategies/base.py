"""Shared types, enums, and cargo JSON parsing for APR v2 strategies."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from c2rust.utils.validation import ValidationResult, categorize_error, ValidationError


class AprStrategyV2(str, Enum):
    BASELINE = "baseline"
    STRUCTURED = "structured_compiler"
    DIAGNOSE_THEN_PATCH = "diagnose_then_patch"
    MEMORY_REFLEXION = "memory_reflexion"


@dataclass
class CargoJsonError:
    """One compiler error parsed from `cargo check --message-format=json`."""

    code: str                       # e.g. "E0425"
    message: str                    # e.g. "cannot find value `foo` in this scope"
    file: str                       # e.g. "src/translated/sds.rs"
    line_start: int
    col_start: int
    label: str                      # span annotation label
    suggested_replacement: str | None
    rendered: str                   # full human-readable error block from rustc

    def to_validation_error(self) -> ValidationError:
        """Convert to ValidationError for compatibility with existing file-selection logic."""
        return ValidationError(
            file=self.file,
            line=self.line_start,
            column=self.col_start,
            code=self.code,
            message=self.message,
            category=categorize_error(self.code, self.message),
            raw=self.rendered,
        )


@dataclass
class MemoryEntry:
    """Records one attempt's outcome for the Reflexion memory block (Strategy 4)."""

    attempt: int
    targeted_error_code: str
    targeted_error_message: str     # first 100 chars of the targeted error message
    diagnosis_summary: str          # full Call-1 diagnosis text
    errors_before: int
    errors_after: int
    status: str                     # "applied" | "reverted_regression" | "rejected_guardrail"


@dataclass
class StrategyRunResult:
    """Returned by every strategy's run() function."""

    patched_code: str
    prompt_tokens: int
    completion_tokens: int
    diagnosis: str          # empty string for S1 and S2
    prompts: list[str]      # [single_prompt] for S1/S2; [diagnose, patch] for S3/S4


def run_cargo_check_json(
    project_dir: str | Path,
) -> tuple[ValidationResult, list[CargoJsonError]]:
    """Run `cargo check --message-format=json` and return a ValidationResult plus
    structured CargoJsonError list.

    The ValidationResult.errors contains the same errors converted to ValidationError
    objects so they can be used with the existing file-selection / priority logic.
    The ValidationResult.raw_output contains the concatenated `rendered` fields
    (i.e. the human-readable terminal output reconstructed from JSON).
    """
    root = Path(project_dir)
    try:
        result = subprocess.run(
            ["cargo", "check", "--message-format=json", "--color", "never"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        empty = ValidationResult(
            success=False,
            errors=[],
            raw_output="cargo not found. Install the Rust toolchain.",
            validator="cargo-check-json",
        )
        return empty, []
    except subprocess.TimeoutExpired:
        empty = ValidationResult(
            success=False,
            errors=[],
            raw_output="cargo check timed out after 5 minutes.",
            validator="cargo-check-json",
        )
        return empty, []

    success = result.returncode == 0
    json_errors: list[CargoJsonError] = []
    rendered_parts: list[str] = []

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get("reason") != "compiler-message":
            continue

        msg = obj.get("message", {})
        if msg.get("level") != "error":
            continue

        rendered = msg.get("rendered", "")
        if rendered:
            rendered_parts.append(rendered.rstrip())

        code_obj = msg.get("code") or {}
        error_code = code_obj.get("code") or "RUST0000"
        error_message = msg.get("message", "")

        # Prefer the primary span; fall back to the first available span.
        spans = msg.get("spans", [])
        primary = [s for s in spans if s.get("is_primary")]
        span = primary[0] if primary else (spans[0] if spans else {})

        raw_file = span.get("file_name", "unknown")
        # Normalise to a path relative to the project root.
        try:
            raw_file = str(Path(raw_file).resolve().relative_to(root.resolve()))
        except (ValueError, TypeError):
            pass

        json_errors.append(
            CargoJsonError(
                code=error_code,
                message=error_message,
                file=raw_file,
                line_start=span.get("line_start", 0),
                col_start=span.get("column_start", 0),
                label=span.get("label") or "",
                suggested_replacement=span.get("suggested_replacement"),
                rendered=rendered,
            )
        )

    rendered_output = "\n".join(rendered_parts)

    # Build a ValidationResult that the existing runner helpers can consume.
    v_errors = [e.to_validation_error() for e in json_errors] if not success else []
    validation = ValidationResult(
        success=success,
        errors=v_errors,
        raw_output=rendered_output,
        validator="cargo-check-json",
    )
    return validation, json_errors
