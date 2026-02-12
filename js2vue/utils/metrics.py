"""
Metrics collection and export for thesis quantitative analysis.
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from js2vue.utils.validation import ErrorCategory, ValidationError


@dataclass
class RepairAttempt:
    """Record of a single repair attempt."""
    iteration: int
    files_modified: List[str]
    error_ids_targeted: List[str]
    repair_strategy: str
    errors_before: int
    errors_after: int
    runtime_errors_before: int
    runtime_errors_after: int
    success: bool                      # Did we reduce errors?
    timestamp: str


@dataclass
class RepairHistory:
    """Complete repair history for a translation run."""
    attempts: List[RepairAttempt] = field(default_factory=list)

    def get_stuck_errors(self, error_reports: List) -> List[str]:
        """
        Find error IDs that persist across multiple iterations.

        Args:
            error_reports: List of ErrorReport objects from each iteration

        Returns:
            List of error IDs that appear in 2+ consecutive reports
        """
        if len(error_reports) < 2:
            return []

        # Track errors that appear in consecutive reports
        stuck_errors = []
        for i in range(len(error_reports) - 1):
            current_ids = {e.error_id for e in error_reports[i].errors}
            next_ids = {e.error_id for e in error_reports[i + 1].errors}
            stuck_errors.extend(current_ids & next_ids)  # Intersection

        return list(set(stuck_errors))


@dataclass
class TranslationMetrics:
    """
    Metrics for a single translation run (thesis quantitative data).

    These metrics directly support thesis research questions:
    - RQ1: Type inference quality (errors_by_category)
    - RQ2: APRA effectiveness (initial vs. final error counts, ERF)
    - RQ3: Chunk vs. assembly repair (repair_iterations, iteration_deltas)
    """
    # Dataset identification
    dataset_name: str
    pipeline_mode: str                # "single" or "multi"

    # File statistics
    files_translated: int
    files_with_errors: int

    # Error metrics
    initial_error_count: int
    final_error_count: int
    error_reduction_factor: float     # ERF = initial / final (or 0 if final = 0)

    # Template-script coherence (RQ2 specific metric)
    template_script_coherence_errors: int

    # Categorized errors (RQ1 analysis)
    errors_by_category: Dict[str, int] = field(default_factory=dict)

    # Repair metrics (RQ2, RQ3)
    repair_iterations: int = 0        # Total APRA iterations
    iteration_deltas: List[int] = field(default_factory=list)  # Error reduction per iteration

    # NEW: Runtime error tracking
    runtime_errors: int = 0
    runtime_error_categories: Dict[str, int] = field(default_factory=dict)
    npm_errors: int = 0

    # NEW: Error report metadata
    error_report_path: str = ""           # Path to generated .md report
    error_analysis_tokens: int = 0        # Tokens used by runner agent

    # NEW: APRA effectiveness (with runtime feedback)
    repair_effectiveness_by_type: Dict[str, float] = field(default_factory=dict)

    # NEW: Repair history tracking (APRA iterations)
    repair_history: 'RepairHistory' = field(default_factory=lambda: RepairHistory())

    # Resource metrics
    tokens_used: Dict[str, int] = field(default_factory=dict)  # {prompt: X, completion: Y}
    timing_seconds: float = 0.0

    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    model_provider: str = ""
    model_id: str = ""


class MetricsCollector:
    """
    Collects and exports metrics throughout a translation pipeline run.
    """

    def __init__(self, dataset_name: str, pipeline_mode: str):
        """
        Initialize metrics collector.

        Args:
            dataset_name: Name of the dataset being processed
            pipeline_mode: "single" or "multi"
        """
        self.dataset_name = dataset_name
        self.pipeline_mode = pipeline_mode

        # Accumulators
        self.files_translated = 0
        self.initial_errors: List[ValidationError] = []
        self.final_errors: List[ValidationError] = []
        self.repair_iterations = 0
        self.iteration_deltas: List[int] = []
        self.tokens_prompt = 0
        self.tokens_completion = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

        # NEW: Runtime error tracking
        self.runtime_errors_list: List = []  # Will hold RuntimeError objects
        self.npm_errors_list: List[str] = []
        self.error_report_path_str: str = ""
        self.error_analysis_tokens_count: int = 0

    def start_timer(self):
        """Starts the timing measurement."""
        import time
        self.start_time = time.time()

    def stop_timer(self):
        """Stops the timing measurement."""
        import time
        self.end_time = time.time()

    def increment_files_translated(self):
        """Increments the file counter."""
        self.files_translated += 1

    def record_initial_errors(self, errors: List[ValidationError]):
        """
        Records initial validation errors (before any repair).

        Args:
            errors: List of validation errors
        """
        self.initial_errors = errors

    def record_final_errors(self, errors: List[ValidationError]):
        """
        Records final validation errors (after repair, or same as initial for single-pass).

        Args:
            errors: List of validation errors
        """
        self.final_errors = errors

    def record_repair_iteration(self, errors_before: int, errors_after: int):
        """
        Records a repair iteration's error reduction.

        Args:
            errors_before: Error count before this iteration
            errors_after: Error count after this iteration
        """
        self.repair_iterations += 1
        delta = errors_before - errors_after
        self.iteration_deltas.append(delta)

    def add_tokens(self, prompt_tokens: int, completion_tokens: int):
        """
        Adds token usage from an LLM call.

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
        """
        self.tokens_prompt += prompt_tokens
        self.tokens_completion += completion_tokens

    def record_runtime_errors(self, errors: List):
        """
        Records runtime errors in metrics.

        Args:
            errors: List of RuntimeError objects
        """
        self.runtime_errors_list = errors

    def record_error_report(self, error_report_path: Path, analysis_tokens: int = 0):
        """
        Save error report path and track analysis token usage.

        Args:
            error_report_path: Path to the generated error report .md file
            analysis_tokens: Number of tokens used by runner agent
        """
        self.error_report_path_str = str(error_report_path)
        self.error_analysis_tokens_count = analysis_tokens

    def compute_metrics(self, model_provider: str, model_id: str) -> TranslationMetrics:
        """
        Computes final metrics from collected data.

        Args:
            model_provider: LLM provider name (e.g., "openai", "gemini")
            model_id: Model identifier (e.g., "gpt-4o")

        Returns:
            TranslationMetrics object ready for export
        """
        initial_count = len(self.initial_errors)
        final_count = len(self.final_errors)

        # Compute ERF (Error Reduction Factor)
        if final_count == 0 and initial_count > 0:
            erf = float('inf')  # Perfect repair
        elif initial_count == 0:
            erf = 0.0
        else:
            erf = initial_count / final_count if final_count > 0 else initial_count

        # Count files with errors
        files_with_errors = len(set(e.file for e in self.final_errors))

        # Categorize errors
        category_counts = {}
        for category in ErrorCategory:
            count = sum(1 for e in self.final_errors if e.category == category)
            if count > 0:
                category_counts[category.value] = count

        # Count template-script coherence errors
        coherence_errors = sum(
            1 for e in self.final_errors
            if e.category == ErrorCategory.TEMPLATE_BINDING
        )

        # Compute timing
        timing = 0.0
        if self.start_time and self.end_time:
            timing = self.end_time - self.start_time

        # Count runtime errors by type
        runtime_error_categories = {}
        for error in self.runtime_errors_list:
            error_type = getattr(error, 'error_type', 'unknown')
            runtime_error_categories[error_type] = runtime_error_categories.get(error_type, 0) + 1

        return TranslationMetrics(
            dataset_name=self.dataset_name,
            pipeline_mode=self.pipeline_mode,
            files_translated=self.files_translated,
            files_with_errors=files_with_errors,
            initial_error_count=initial_count,
            final_error_count=final_count,
            error_reduction_factor=erf,
            template_script_coherence_errors=coherence_errors,
            errors_by_category=category_counts,
            repair_iterations=self.repair_iterations,
            iteration_deltas=self.iteration_deltas,
            runtime_errors=len(self.runtime_errors_list),
            runtime_error_categories=runtime_error_categories,
            npm_errors=len(self.npm_errors_list),
            error_report_path=self.error_report_path_str,
            error_analysis_tokens=self.error_analysis_tokens_count,
            tokens_used={
                "prompt": self.tokens_prompt,
                "completion": self.tokens_completion,
                "total": self.tokens_prompt + self.tokens_completion
            },
            timing_seconds=timing,
            model_provider=model_provider,
            model_id=model_id
        )

    def export_to_json(self, metrics: TranslationMetrics, output_path: Path):
        """
        Exports metrics to a JSON file.

        Args:
            metrics: TranslationMetrics object
            output_path: Path to write JSON file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(asdict(metrics), f, indent=2)

        print(f"\n✅ Metrics exported to: {output_path}")


def load_metrics_from_json(json_path: Path) -> TranslationMetrics:
    """
    Loads metrics from a JSON file.

    Args:
        json_path: Path to metrics JSON file

    Returns:
        TranslationMetrics object

    Raises:
        FileNotFoundError: If JSON file doesn't exist
        json.JSONDecodeError: If JSON is malformed
    """
    with open(json_path, 'r') as f:
        data = json.load(f)

    return TranslationMetrics(**data)
