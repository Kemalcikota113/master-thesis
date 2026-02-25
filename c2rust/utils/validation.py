"""Compile-only validation via cargo check and diagnostic parsing."""

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ErrorCategory(Enum):
    SYNTAX = "syntax"
    TYPE = "type"
    BORROW = "borrow_checker"
    UNRESOLVED = "unresolved_symbol"
    TRAIT = "trait"
    OTHER = "other"


@dataclass
class ValidationError:
    file: str
    line: int
    column: int
    code: str
    message: str
    category: ErrorCategory
    raw: str = ""


@dataclass
class ValidationResult:
    success: bool
    errors: list[ValidationError] = field(default_factory=list)
    raw_output: str = ""
    validator: str = "cargo-check"


def categorize_error(code: str, message: str) -> ErrorCategory:
    msg = message.lower()
    if code.startswith("E03") or "expected" in msg or "mismatched" in msg:
        return ErrorCategory.SYNTAX
    if code.startswith("E05") or code.startswith("E06"):
        return ErrorCategory.TYPE
    if code.startswith("E04") or "cannot find" in msg:
        return ErrorCategory.UNRESOLVED
    if code.startswith("E02") or "borrow" in msg or "moved value" in msg:
        return ErrorCategory.BORROW
    if "trait" in msg or code.startswith("E02"):
        return ErrorCategory.TRAIT
    return ErrorCategory.OTHER


def parse_cargo_check_output(output: str, project_dir: Path) -> list[ValidationError]:
    """Parse rustc-style cargo check diagnostics from plain text output."""
    errors: list[ValidationError] = []
    lines = output.splitlines()

    start_re = re.compile(r"^error(?:\[(?P<code>E\d{4})\])?:\s*(?P<msg>.+)$")
    loc_re = re.compile(r"^\s*-->\s+(?P<file>.+?):(?P<line>\d+):(?P<col>\d+)")

    current_code = ""
    current_msg = ""

    for idx, line in enumerate(lines):
        start = start_re.match(line)
        if start:
            current_code = start.group("code") or "RUST0000"
            current_msg = start.group("msg").strip()

            file_path = "unknown"
            line_num = 0
            col_num = 0

            for follow in lines[idx + 1 : idx + 7]:
                loc = loc_re.match(follow)
                if not loc:
                    continue
                raw_file = loc.group("file")
                try:
                    file_path = str(Path(raw_file).resolve().relative_to(project_dir.resolve()))
                except ValueError:
                    file_path = raw_file
                line_num = int(loc.group("line"))
                col_num = int(loc.group("col"))
                break

            errors.append(
                ValidationError(
                    file=file_path,
                    line=line_num,
                    column=col_num,
                    code=current_code,
                    message=current_msg,
                    category=categorize_error(current_code, current_msg),
                    raw=line,
                )
            )

    return errors


def run_cargo_check(project_dir: str | Path) -> ValidationResult:
    """Run cargo check and return structured results."""
    root = Path(project_dir)
    if not root.exists():
        raise FileNotFoundError(f"Project directory does not exist: {root}")

    try:
        result = subprocess.run(
            ["cargo", "check", "--color", "never"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        return ValidationResult(
            success=False,
            errors=[],
            raw_output="cargo not found. Install Rust toolchain.",
        )
    except subprocess.TimeoutExpired:
        return ValidationResult(
            success=False,
            errors=[],
            raw_output="cargo check timed out after 5 minutes",
        )

    output = (result.stdout or "") + (result.stderr or "")
    success = result.returncode == 0
    errors = [] if success else parse_cargo_check_output(output, root)
    return ValidationResult(success=success, errors=errors, raw_output=output)
