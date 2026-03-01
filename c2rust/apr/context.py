"""Context building utilities for APR strategies."""

import re
from enum import Enum
from pathlib import Path

from c2rust.utils.validation import ValidationError


class AprStrategy(str, Enum):
    ERROR_ONLY = "error_only"
    ERROR_PLUS_RUST = "error_plus_rust"
    ERROR_RUST_C = "error_rust_c"
    ERROR_RUST_C_RELATED = "error_rust_c_related"


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def map_rust_file_to_c_source(dataset_path: Path, rust_file: Path) -> Path | None:
    """Best-effort map from translated Rust file to original C file."""
    rust_stem = normalize_name(rust_file.stem)
    candidates = sorted(dataset_path.rglob("*.c"))
    if not candidates:
        return None

    # Exact normalized stem first.
    for c_path in candidates:
        if normalize_name(c_path.stem) == rust_stem:
            return c_path

    # Prefix/substring heuristic fallback.
    for c_path in candidates:
        c_norm = normalize_name(c_path.stem)
        if c_norm in rust_stem or rust_stem in c_norm:
            return c_path

    return None


def _extract_imported_translated_modules(rust_code: str) -> list[str]:
    """Extract local module references from use/imports."""
    mods: set[str] = set()
    patterns = [
        r"use\s+crate::translated::([a-zA-Z0-9_]+)",
        r"mod\s+([a-zA-Z0-9_]+)\s*;",
        r"super::([a-zA-Z0-9_]+)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, rust_code):
            mods.add(m.group(1))
    return sorted(mods)


def _load_related_rust_context(
    project_dir: Path,
    failing_rust_file: Path,
    max_chars: int = 40000,
    max_blocks: int = 12,
) -> tuple[str, list[str]]:
    """Load bounded related Rust context for strategy 4."""
    try:
        current_code = failing_rust_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "", []

    module_names = _extract_imported_translated_modules(current_code)
    translated_dir = project_dir / "src" / "translated"
    blocks: list[str] = []
    used_files: list[str] = []
    total = 0

    for module in module_names[:max_blocks]:
        related_path = translated_dir / f"{module}.rs"
        if not related_path.exists():
            continue
        if related_path.resolve() == failing_rust_file.resolve():
            continue

        try:
            content = related_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        block = f"// RELATED FILE: src/translated/{related_path.name}\n{content.strip()}\n"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 500:
                blocks.append(block[:remaining])
                used_files.append(f"src/translated/{related_path.name}")
            break

        blocks.append(block)
        used_files.append(f"src/translated/{related_path.name}")
        total += len(block)

    return "\n".join(blocks), used_files


def _error_block(error: ValidationError, raw_compile_output: str) -> str:
    return (
        f"Compiler error code: {error.code}\n"
        f"File: {error.file}:{error.line}:{error.column}\n"
        f"Category: {error.category.value}\n"
        f"Message: {error.message}\n"
    )


def _compiler_excerpt(raw_compile_output: str, max_lines: int = 120) -> str:
    preview = raw_compile_output.splitlines()[:max_lines]
    return "\n".join(preview)


def _line_window(text: str, line: int, radius: int = 30) -> str:
    lines = text.splitlines()
    if not lines:
        return ""
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    window = []
    for idx in range(start, end + 1):
        window.append(f"{idx}: {lines[idx - 1]}")
    return "\n".join(window)


def build_apr_prompt(
    strategy: AprStrategy,
    error: ValidationError,
    raw_compile_output: str,
    failing_rust_file: Path,
    dataset_path: Path,
    project_dir: Path,
    attempt_memory: list[str] | None = None,
) -> tuple[str, dict[str, object]]:
    """Build strategy-specific prompt and lightweight context metadata."""
    rust_code = failing_rust_file.read_text(encoding="utf-8", errors="ignore")
    c_source_path = map_rust_file_to_c_source(dataset_path, failing_rust_file)
    c_source = ""
    if c_source_path and c_source_path.exists():
        c_source = c_source_path.read_text(encoding="utf-8", errors="ignore")

    error_line_window = _line_window(rust_code, error.line, radius=35)
    c_line_window = _line_window(c_source, error.line, radius=35) if c_source else ""

    related_context = ""
    related_files: list[str] = []
    if strategy == AprStrategy.ERROR_RUST_C_RELATED:
        related_context, related_files = _load_related_rust_context(project_dir, failing_rust_file)

    lines: list[str] = []
    lines.append("Fix the target Rust file to address the current compile error.")
    lines.append("Return ONLY the complete updated target Rust file content.")
    lines.append("")
    lines.append("## Current Compiler Error")
    lines.append(_error_block(error, raw_compile_output))

    if attempt_memory:
        lines.append("")
        lines.append("## Previous Attempt Memory")
        lines.append("Avoid repeating failed patterns from earlier attempts.")
        for item in attempt_memory[-3:]:
            lines.append(f"- {item}")

    if strategy in {
        AprStrategy.ERROR_PLUS_RUST,
        AprStrategy.ERROR_RUST_C,
        AprStrategy.ERROR_RUST_C_RELATED,
    }:
        lines.append("")
        lines.append("## Compiler Output Excerpt")
        lines.append("```")
        lines.append(_compiler_excerpt(raw_compile_output, max_lines=160))
        lines.append("```")

    lines.append("")
    lines.append("## Target Rust Error Region")
    lines.append("```rust")
    lines.append(error_line_window)
    lines.append("```")

    lines.append("")
    lines.append(f"## Target Rust File: {failing_rust_file}")
    lines.append("```rust")
    lines.append(rust_code)
    lines.append("```")

    if strategy in {AprStrategy.ERROR_RUST_C, AprStrategy.ERROR_RUST_C_RELATED} and c_source:
        lines.append("")
        lines.append(f"## Source C Reference: {c_source_path}")
        lines.append("```c")
        lines.append(c_source)
        lines.append("```")

        if c_line_window:
            lines.append("")
            lines.append("## Source C Error Region (approximate)")
            lines.append("```c")
            lines.append(c_line_window)
            lines.append("```")

    if strategy == AprStrategy.ERROR_RUST_C_RELATED and related_context:
        lines.append("")
        lines.append("## Related Rust Context")
        lines.append("```rust")
        lines.append(related_context)
        lines.append("```")

    metadata = {
        "strategy": strategy.value,
        "source_file_included": (
            strategy in {AprStrategy.ERROR_RUST_C, AprStrategy.ERROR_RUST_C_RELATED} and bool(c_source)
        ),
        "source_file": (
            str(c_source_path)
            if strategy in {AprStrategy.ERROR_RUST_C, AprStrategy.ERROR_RUST_C_RELATED} and c_source_path
            else ""
        ),
        "related_files_count": len(related_files),
        "related_files": related_files,
    }
    return "\n".join(lines), metadata
