"""Metrics collection and export for c2rust runs."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from c2rust.utils.fidelity import FidelityReport
from c2rust.utils.validation import ValidationError


@dataclass
class TranslationMetrics:
    dataset_name: str
    pipeline_mode: str
    files_discovered: int
    files_translated: int
    translation_attempts: int
    header_files_used_for_context: int
    compile_success: bool
    initial_error_count: int
    final_error_count: int
    errors_by_category: dict[str, int] = field(default_factory=dict)
    files_with_errors: int = 0
    tokens_used: dict[str, int] = field(default_factory=dict)
    timing_seconds: float = 0.0
    compile_output_path: str = ""
    fidelity_report_path: str = ""
    fidelity_gate_passed: bool = False
    fidelity_gate_mode: str = "strict"
    fidelity_strict_coverage: float = 0.0
    fidelity_relaxed_coverage: float = 0.0
    expected_function_count: int = 0
    translated_function_count: int = 0
    missing_function_count: int = 0
    placeholder_count: int = 0
    possible_truncation: bool = False
    pre_compile_gate_failed: bool = False
    compile_skipped: bool = False
    compile_skipped_reason: str = ""
    translation_diagnostics_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    model_provider: str = ""
    model_id: str = ""


class MetricsCollector:
    """Collect and compute translation metrics for one run."""

    def __init__(self, dataset_name: str, pipeline_mode: str):
        self.dataset_name = dataset_name
        self.pipeline_mode = pipeline_mode
        self.files_discovered = 0
        self.files_translated = 0
        self.translation_attempts = 0
        self.header_files_used_for_context = 0
        self.initial_errors: list[ValidationError] = []
        self.final_errors: list[ValidationError] = []
        self.tokens_prompt = 0
        self.tokens_completion = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.compile_output_path = ""
        self.fidelity_report_path = ""
        self.fidelity_report = FidelityReport()
        self.translation_diagnostics_path = ""
        self.pre_compile_gate_failed = False
        self.compile_skipped = False
        self.compile_skipped_reason = ""

    def start_timer(self):
        import time

        self.start_time = time.time()

    def stop_timer(self):
        import time

        self.end_time = time.time()

    def add_tokens(self, prompt_tokens: int, completion_tokens: int):
        self.tokens_prompt += prompt_tokens
        self.tokens_completion += completion_tokens

    def record_discovered_files(self, count: int):
        self.files_discovered = count

    def increment_files_translated(self):
        self.files_translated += 1
        self.translation_attempts += 1

    def record_header_context_count(self, count: int):
        self.header_files_used_for_context = count

    def record_initial_errors(self, errors: list[ValidationError]):
        self.initial_errors = errors

    def record_final_errors(self, errors: list[ValidationError]):
        self.final_errors = errors

    def record_compile_output_path(self, path: Path):
        self.compile_output_path = str(path)

    def record_fidelity_report(self, report: FidelityReport, path: Path):
        self.fidelity_report = report
        self.fidelity_report_path = str(path)

    def record_translation_diagnostics_path(self, path: Path):
        self.translation_diagnostics_path = str(path)

    def record_pre_compile_gate_failure(self, reason: str):
        self.pre_compile_gate_failed = True
        self.compile_skipped = True
        self.compile_skipped_reason = reason

    def compute_metrics(self, model_provider: str, model_id: str, compile_success: bool) -> TranslationMetrics:
        if self.start_time is None:
            timing = 0.0
        elif self.end_time is None:
            import time

            timing = time.time() - self.start_time
        else:
            timing = self.end_time - self.start_time

        category_counts: dict[str, int] = {}
        files_with_errors = set()
        for err in self.final_errors:
            category_counts[err.category.value] = category_counts.get(err.category.value, 0) + 1
            if err.file and err.file != "unknown":
                files_with_errors.add(err.file)

        return TranslationMetrics(
            dataset_name=self.dataset_name,
            pipeline_mode=self.pipeline_mode,
            files_discovered=self.files_discovered,
            files_translated=self.files_translated,
            translation_attempts=self.translation_attempts,
            header_files_used_for_context=self.header_files_used_for_context,
            compile_success=compile_success,
            initial_error_count=len(self.initial_errors),
            final_error_count=len(self.final_errors),
            errors_by_category=category_counts,
            files_with_errors=len(files_with_errors),
            tokens_used={
                "prompt": self.tokens_prompt,
                "completion": self.tokens_completion,
                "total": self.tokens_prompt + self.tokens_completion,
            },
            timing_seconds=timing,
            compile_output_path=self.compile_output_path,
            fidelity_report_path=self.fidelity_report_path,
            fidelity_gate_passed=self.fidelity_report.gate_passed,
            fidelity_gate_mode=self.fidelity_report.gate_mode,
            fidelity_strict_coverage=self.fidelity_report.strict_coverage,
            fidelity_relaxed_coverage=self.fidelity_report.relaxed_coverage,
            expected_function_count=len(self.fidelity_report.expected_c_functions),
            translated_function_count=len(self.fidelity_report.translated_rust_functions),
            missing_function_count=len(self.fidelity_report.missing_functions),
            placeholder_count=self.fidelity_report.placeholder_count,
            possible_truncation=self.fidelity_report.possible_truncation,
            pre_compile_gate_failed=self.pre_compile_gate_failed,
            compile_skipped=self.compile_skipped,
            compile_skipped_reason=self.compile_skipped_reason,
            translation_diagnostics_path=self.translation_diagnostics_path,
            model_provider=model_provider,
            model_id=model_id,
        )

    @staticmethod
    def export_to_json(metrics: TranslationMetrics, output_path: str | Path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(asdict(metrics), indent=2), encoding="utf-8")
