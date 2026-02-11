"""
Validation utilities for running vue-tsc and eslint, parsing errors.
"""

import re
import subprocess
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List


class ErrorCategory(Enum):
    """Categories of validation errors for thesis analysis."""
    TYPE_INFERENCE = "type_inference"           # TypeScript type errors
    TEMPLATE_BINDING = "template_binding"       # Template/script binding mismatches
    MISSING_IMPORT = "missing_import"           # Missing import statements
    SYNTAX = "syntax"                           # Syntax errors
    OTHER = "other"                             # Uncategorized errors


@dataclass
class ValidationError:
    """Structured representation of a validation error."""
    file: str                      # Relative file path
    line: int                      # Line number (0 if unknown)
    code: str                      # Error code (e.g., "TS2339", "vue/no-unused-vars")
    message: str                   # Error message
    category: ErrorCategory        # Categorized error type
    raw: str = ""                  # Raw error output (for debugging)


@dataclass
class ValidationResult:
    """Result of a validation run."""
    success: bool                          # True if no errors
    errors: List[ValidationError] = field(default_factory=list)
    raw_output: str = ""                   # Full output from validator
    validator: str = "vue-tsc"             # Which validator was used


def categorize_error(error_code: str, message: str) -> ErrorCategory:
    """
    Categorizes an error based on its code and message content.

    Args:
        error_code: Error code (e.g., "TS2339", "vue/no-unused-vars")
        message: Error message text

    Returns:
        ErrorCategory enum value
    """
    message_lower = message.lower()

    # Type inference errors
    type_patterns = [
        r'cannot find name',
        r'property .* does not exist',
        r'type .* is not assignable',
        r'has no exported member',
        r'implicit.*any.*type',
        r'expected.*arguments.*but got'
    ]
    if any(re.search(pattern, message_lower) for pattern in type_patterns):
        return ErrorCategory.TYPE_INFERENCE

    # Template-script binding errors (thesis-specific metric)
    binding_patterns = [
        r'not defined in template',
        r'used in template but not declared',
        r'property.*not found on.*template',
        r'ref is not defined',
        r'computed.*not found'
    ]
    if any(re.search(pattern, message_lower) for pattern in binding_patterns):
        return ErrorCategory.TEMPLATE_BINDING

    # Missing imports
    import_patterns = [
        r'cannot find module',
        r'module.*has no exported',
        r'could not find.*import'
    ]
    if any(re.search(pattern, message_lower) for pattern in import_patterns):
        return ErrorCategory.MISSING_IMPORT

    # Syntax errors
    syntax_patterns = [
        r'unexpected token',
        r'expected.*but got',
        r'parsing error',
        r'unterminated'
    ]
    if any(re.search(pattern, message_lower) for pattern in syntax_patterns):
        return ErrorCategory.SYNTAX

    return ErrorCategory.OTHER


def parse_vue_tsc_output(output: str, project_dir: Path) -> List[ValidationError]:
    """
    Parses vue-tsc error output into structured ValidationError objects.

    Args:
        output: Raw stdout/stderr from vue-tsc
        project_dir: Root directory of the Vue project (for relativizing paths)

    Returns:
        List of ValidationError objects
    """
    errors = []

    # vue-tsc output format:
    # path/to/file.vue(line,col): error TS####: message
    # OR
    # path/to/file.vue:line:col - error TS####: message

    pattern = re.compile(
        r'(?P<file>[^(:]+)'                      # File path
        r'[\(:)](?P<line>\d+)'                   # Line number
        r'[,:)](?P<col>\d+)?'                    # Column (optional)
        r'[:\)]\s*'
        r'error\s+'
        r'(?P<code>TS\d+)?:?\s*'                 # Error code (optional)
        r'(?P<message>.+)'                       # Message
    )

    for line in output.split('\n'):
        match = pattern.search(line)
        if match:
            file_path = match.group('file').strip()
            line_num = int(match.group('line'))
            code = match.group('code') or 'TS0000'
            message = match.group('message').strip()

            # Relativize file path
            try:
                file_path = str(Path(file_path).relative_to(project_dir))
            except ValueError:
                pass  # Keep absolute path if can't relativize

            category = categorize_error(code, message)

            errors.append(ValidationError(
                file=file_path,
                line=line_num,
                code=code,
                message=message,
                category=category,
                raw=line
            ))

    return errors


def run_vue_tsc(project_dir: str | Path) -> ValidationResult:
    """
    Runs vue-tsc type checker on a Vue project.

    Args:
        project_dir: Path to the Vue project root (contains package.json)

    Returns:
        ValidationResult with success status and parsed errors

    Raises:
        FileNotFoundError: If project_dir doesn't exist
    """
    project_dir = Path(project_dir)

    if not project_dir.exists():
        raise FileNotFoundError(f"Project directory does not exist: {project_dir}")

    # Check if node_modules exists (npm install should have run)
    if not (project_dir / "node_modules").exists():
        raise RuntimeError(
            f"node_modules not found in {project_dir}. "
            "Run 'npm install' first."
        )

    try:
        result = subprocess.run(
            ["npx", "vue-tsc", "--noEmit"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        # vue-tsc exits with non-zero on errors
        success = result.returncode == 0
        output = result.stdout + result.stderr

        errors = parse_vue_tsc_output(output, project_dir) if not success else []

        return ValidationResult(
            success=success,
            errors=errors,
            raw_output=output,
            validator="vue-tsc"
        )

    except subprocess.TimeoutExpired:
        return ValidationResult(
            success=False,
            errors=[],
            raw_output="vue-tsc timed out after 5 minutes",
            validator="vue-tsc"
        )
    except FileNotFoundError:
        return ValidationResult(
            success=False,
            errors=[],
            raw_output="vue-tsc not found. Ensure it's installed in node_modules.",
            validator="vue-tsc"
        )


def run_eslint(project_dir: str | Path) -> ValidationResult:
    """
    Runs ESLint on a Vue project (stub for future implementation).

    Args:
        project_dir: Path to the Vue project root

    Returns:
        ValidationResult (currently always success)

    Note:
        This is a placeholder for future ESLint integration.
        Full implementation requires eslint-plugin-vue configuration.
    """
    # TODO: Implement ESLint validation
    # Will require:
    # - .eslintrc.js configuration with vue-eslint-plugin
    # - Parsing ESLint JSON output
    # - Categorizing ESLint errors

    return ValidationResult(
        success=True,
        errors=[],
        raw_output="ESLint validation not yet implemented",
        validator="eslint"
    )


def count_template_script_coherence_errors(errors: List[ValidationError]) -> int:
    """
    Counts errors related to template-script binding coherence.

    This is a specific metric for thesis research question RQ2.

    Args:
        errors: List of validation errors

    Returns:
        Number of template-script coherence errors
    """
    return sum(1 for e in errors if e.category == ErrorCategory.TEMPLATE_BINDING)


# ============================================================
# RUNTIME VALIDATION (NEW)
# ============================================================

# Import RuntimeError from runtime_capture
try:
    from js2vue.utils.runtime_capture import RuntimeError
except ImportError:
    # Fallback for when runtime_capture is not available
    @dataclass
    class RuntimeError:
        """Fallback RuntimeError definition."""
        file: str
        line: int
        message: str
        error_type: str
        stack: str = ""
        timestamp: str = ""
        component: str = ""
        severity: str = "error"


@dataclass
class RuntimeValidationResult(ValidationResult):
    """
    Extended ValidationResult that includes runtime errors.

    Combines both static validation (vue-tsc) and runtime validation (browser).
    """
    runtime_errors: List[RuntimeError] = field(default_factory=list)
    npm_errors: List[str] = field(default_factory=list)


def run_runtime_validation(
    project_dir: Path,
    capture_duration: int = 30,
    port: int = 5173
) -> RuntimeValidationResult:
    """
    Run both static (vue-tsc) and runtime (browser) validation.

    Args:
        project_dir: Path to Vue project root
        capture_duration: How long to capture runtime errors (seconds)
        port: Port for Vite dev server

    Returns:
        RuntimeValidationResult with both static and runtime errors
    """
    # Import here to avoid circular dependencies
    from js2vue.utils.runtime_capture import capture_runtime_errors

    # Step 1: Run static validation (existing)
    static_result = run_vue_tsc(project_dir)

    # Step 2: Run runtime validation (new)
    print(f"   Starting runtime error capture ({capture_duration}s)...")
    runtime_errors = asyncio.run(
        capture_runtime_errors(project_dir, port, capture_duration)
    )
    print(f"   Runtime errors captured: {len(runtime_errors)}")

    # Step 3: Combine results
    return RuntimeValidationResult(
        success=static_result.success and len(runtime_errors) == 0,
        errors=static_result.errors,
        runtime_errors=runtime_errors,
        npm_errors=[],  # TODO: implement npm error parsing
        raw_output=static_result.raw_output,
        validator=static_result.validator
    )


def parse_npm_errors(npm_output: str) -> List[str]:
    """
    Extract npm/vite error messages from install/build output.

    Args:
        npm_output: Raw output from npm install or npm run build

    Returns:
        List of error messages
    """
    errors = []

    # Parse npm ERR! lines
    for line in npm_output.split('\n'):
        if 'npm ERR!' in line or 'npm WARN' in line:
            # Clean up the error message
            msg = line.replace('npm ERR!', '').replace('npm WARN', '').strip()
            if msg:  # Skip empty lines
                errors.append(msg)

    return errors
