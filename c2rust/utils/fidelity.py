"""Translation fidelity checks for C->Rust outputs."""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class FidelityReport:
    """Coverage report between C-defined symbols and translated Rust symbols."""

    expected_c_functions: list[str] = field(default_factory=list)
    translated_rust_functions: list[str] = field(default_factory=list)
    strict_matched_functions: list[str] = field(default_factory=list)
    relaxed_matched_functions: list[str] = field(default_factory=list)
    missing_functions: list[str] = field(default_factory=list)
    strict_coverage: float = 0.0
    relaxed_coverage: float = 0.0
    gate_mode: str = "strict"
    placeholder_count: int = 0
    placeholder_hits: list[str] = field(default_factory=list)
    possible_truncation: bool = False
    truncation_reasons: list[str] = field(default_factory=list)
    gate_passed: bool = False


def _normalize_symbol(name: str) -> str:
    return re.sub(r"_+", "", name).lower()


def extract_c_defined_functions(c_files: list[tuple[str, Path]]) -> list[str]:
    """Extract function names defined in C source files."""
    # Includes common signatures such as:
    #   sds sdsnewlen(const void *init, size_t initlen) {
    #   static inline int foo(...) {
    # Avoids control-flow constructs and prototypes ending with ';'.
    definition_re = re.compile(
        r"^\s*(?:static\s+)?(?:inline\s+)?(?:[A-Za-z_][\w\s\*]*\s+)+"
        r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{",
        flags=re.MULTILINE,
    )

    excluded = {"if", "for", "while", "switch"}
    names: set[str] = set()

    for _, abs_path in c_files:
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for match in definition_re.finditer(content):
            name = match.group("name")
            if name in excluded:
                continue
            names.add(name)

    return sorted(names)


def _strip_c_comments(text: str) -> str:
    """Remove C/C++ comments for simpler prototype parsing."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    return text


def extract_c_public_api_functions(header_files: list[tuple[str, Path]]) -> list[str]:
    """Extract public function prototypes from C headers.

    This intentionally focuses on declarations ending with ';' and excludes
    static/typedef/macro/struct declarations. It is used as the primary
    fidelity baseline to avoid over-penalizing missing private helper symbols.
    """
    names: set[str] = set()

    # Matches common C prototypes, including multi-line signatures.
    prototype_re = re.compile(
        r"^\s*(?!static\b)(?!typedef\b)(?!struct\b)(?!enum\b)(?!union\b)(?!#)"
        r"(?:[A-Za-z_][\w\s\*]*\s+)+(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*;",
        flags=re.MULTILINE,
    )

    for _, abs_path in header_files:
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        content = _strip_c_comments(content)

        for match in prototype_re.finditer(content):
            name = match.group("name")
            # Exclude likely macro-like pseudo symbols.
            if name.isupper():
                continue
            names.add(name)

    return sorted(names)


def extract_rust_functions(rust_files: list[Path]) -> list[str]:
    """Extract function names from translated Rust files."""
    rust_re = re.compile(r"^\s*(?:pub\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
    names: set[str] = set()

    for file_path in rust_files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for match in rust_re.finditer(content):
            names.add(match.group(1))

    return sorted(names)


def analyze_rust_output_quality(rust_code: str) -> tuple[list[str], list[str]]:
    """Detect placeholder markers and possible truncation patterns."""
    placeholder_patterns = [
        r"\bTODO\b",
        r"\btodo!\s*\(",
        r"\bunimplemented!\s*\(",
        r"\bpanic!\s*\(\s*\"TODO",
        r"\breturn\s+Default::default\(\)\s*;",
    ]
    placeholder_hits: list[str] = []
    lowered = rust_code.lower()

    for pattern in placeholder_patterns:
        if re.search(pattern, rust_code, flags=re.IGNORECASE):
            placeholder_hits.append(pattern)

    truncation_reasons: list[str] = []
    if rust_code.count("{") != rust_code.count("}"):
        truncation_reasons.append("unbalanced_braces")
    if rust_code.rstrip().endswith(("=>", "=", ",", "(", "{")):
        truncation_reasons.append("abrupt_file_ending")
    if lowered.endswith("todo") or lowered.endswith("todo."):
        truncation_reasons.append("ends_with_todo")

    return placeholder_hits, truncation_reasons


def analyze_rust_files_quality(rust_files: list[Path]) -> tuple[int, list[str], bool, list[str]]:
    """Aggregate placeholder and truncation diagnostics across files."""
    all_hits: list[str] = []
    all_reasons: list[str] = []
    for file_path in rust_files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        hits, reasons = analyze_rust_output_quality(content)
        all_hits.extend([f"{file_path.name}:{h}" for h in hits])
        all_reasons.extend([f"{file_path.name}:{r}" for r in reasons])

    return len(all_hits), sorted(set(all_hits)), bool(all_reasons), sorted(set(all_reasons))


def compute_fidelity_report(
    expected_functions: list[str],
    rust_functions: list[str],
    min_strict_coverage: float = 0.95,
    min_relaxed_coverage: float = 0.95,
    gate_mode: str = "strict",
    placeholder_count: int = 0,
    placeholder_hits: list[str] | None = None,
    possible_truncation: bool = False,
    truncation_reasons: list[str] | None = None,
) -> FidelityReport:
    """Compute strict/relaxed symbol coverage and gate status."""
    expected_set = set(expected_functions)
    rust_set = set(rust_functions)

    strict_matched = sorted(expected_set & rust_set)
    missing = sorted(expected_set - rust_set)

    rust_norm = {_normalize_symbol(name) for name in rust_set}
    relaxed_matched = sorted(
        name for name in expected_set if _normalize_symbol(name) in rust_norm
    )

    if gate_mode not in {"strict", "relaxed"}:
        raise ValueError("gate_mode must be 'strict' or 'relaxed'")

    expected_count = len(expected_set)
    if expected_count == 0:
        strict_coverage = 1.0
        relaxed_coverage = 1.0
        gate_passed = placeholder_count == 0 and not possible_truncation
    else:
        strict_coverage = len(strict_matched) / expected_count
        relaxed_coverage = len(relaxed_matched) / expected_count
        coverage_ok = (
            strict_coverage >= min_strict_coverage
            if gate_mode == "strict"
            else relaxed_coverage >= min_relaxed_coverage
        )
        gate_passed = (
            coverage_ok
            and placeholder_count == 0
            and not possible_truncation
        )

    return FidelityReport(
        expected_c_functions=sorted(expected_set),
        translated_rust_functions=sorted(rust_set),
        strict_matched_functions=strict_matched,
        relaxed_matched_functions=relaxed_matched,
        missing_functions=missing,
        strict_coverage=strict_coverage,
        relaxed_coverage=relaxed_coverage,
        gate_mode=gate_mode,
        placeholder_count=placeholder_count,
        placeholder_hits=placeholder_hits or [],
        possible_truncation=possible_truncation,
        truncation_reasons=truncation_reasons or [],
        gate_passed=gate_passed,
    )


def export_fidelity_report(report: FidelityReport, output_path: str | Path):
    """Write fidelity report to disk as JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
