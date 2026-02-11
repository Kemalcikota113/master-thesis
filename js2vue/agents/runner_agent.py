"""
Runner Agent: Analyzes, categorizes, and prioritizes errors for APRA.
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Dict, Union
from datetime import datetime

from agno.agent import Agent

from js2vue.utils.validation import ValidationError, ErrorCategory
try:
    from js2vue.utils.runtime_capture import RuntimeError
except ImportError:
    # Fallback for when runtime_capture is not available
    @dataclass
    class RuntimeError:
        file: str
        line: int
        message: str
        error_type: str
        stack: str = ""
        timestamp: str = ""
        component: str = ""
        severity: str = "error"


@dataclass
class ErrorEntry:
    """Single error with analysis metadata."""
    error_id: str              # Unique ID (hash of file+line+message)
    source_error: Union[ValidationError, RuntimeError]  # Original error
    priority: str              # 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
    category: str              # 'import' | 'type' | 'binding' | 'runtime' | 'syntax'
    root_cause: bool           # Is this a root cause or symptom?
    blocks: List[str]          # Error IDs this blocks
    repair_strategy: str       # LLM suggestion for fix approach
    estimated_difficulty: str  # 'easy' | 'medium' | 'hard'


@dataclass
class ErrorReport:
    """Comprehensive error analysis for APRA."""
    timestamp: str
    summary: str                          # LLM summary of issue
    total_errors: int
    errors: List[ErrorEntry]              # Sorted by priority
    dependency_graph: Dict[str, List[str]]  # error_id → blocks these
    recommended_repair_order: List[str]   # Repair in this order

    def to_markdown(self) -> str:
        """Generate markdown report for debugging."""
        lines = []

        # Header
        lines.append("# Error Analysis Report")
        lines.append("")
        lines.append(f"**Generated:** {self.timestamp}")
        lines.append(f"**Total Errors:** {self.total_errors}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(self.summary)
        lines.append("")

        # Errors by priority
        priority_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        for priority in priority_order:
            priority_errors = [e for e in self.errors if e.priority == priority]
            if not priority_errors:
                continue

            lines.append(f"## {priority} Priority Errors ({len(priority_errors)})")
            lines.append("")

            for error in priority_errors:
                lines.append(f"### {error.error_id}: {error.category}")
                lines.append("")
                lines.append(f"- **File:** {error.source_error.file}:{error.source_error.line}")

                # Determine error type
                error_source = "Static" if isinstance(error.source_error, ValidationError) else "Runtime"
                lines.append(f"- **Type:** {error_source} ({error.source_error.error_type if hasattr(error.source_error, 'error_type') else 'validation'})")

                lines.append(f"- **Message:** {error.source_error.message}")
                lines.append(f"- **Root Cause:** {'Yes' if error.root_cause else 'No'}")

                if error.blocks:
                    lines.append(f"- **Blocks:** {', '.join(error.blocks)}")

                lines.append(f"- **Repair Strategy:** {error.repair_strategy}")
                lines.append(f"- **Difficulty:** {error.estimated_difficulty}")
                lines.append("")

        # Dependency graph
        if self.dependency_graph:
            lines.append("## Dependency Graph")
            lines.append("")
            lines.append("```")
            for error_id, blocked_ids in self.dependency_graph.items():
                if blocked_ids:
                    lines.append(f"{error_id}")
                    for blocked_id in blocked_ids:
                        lines.append(f"  └─► {blocked_id}")
            lines.append("```")
            lines.append("")

        # Recommended repair order
        lines.append("## Recommended Repair Order")
        lines.append("")
        for i, error_id in enumerate(self.recommended_repair_order, 1):
            lines.append(f"{i}. {error_id}")
        lines.append("")

        return '\n'.join(lines)


class RunnerAgent:
    """Analyzes errors and guides repair strategy."""

    def __init__(self, model):
        """
        Initialize runner agent.

        Args:
            model: LLM model instance (OpenAIChat or Gemini)
        """
        self.agent = Agent(
            model=model,
            instructions="""You are an expert error analyst for Vue 3 translations from JavaScript.

Your task: Analyze translation errors and help prioritize repairs.

For each error:
1. Identify if it's a root cause or symptom of another error
   - Root causes: Missing imports, incorrect module setup, fundamental type mismatches
   - Symptoms: Downstream type errors, template binding issues caused by missing imports

2. Assign priority based on impact:
   - CRITICAL: Blocks app initialization or compilation (missing Vue imports, syntax errors)
   - HIGH: Major feature broken, runtime exceptions (undefined refs, failed component mounts)
   - MEDIUM: Type errors, warnings that don't break functionality
   - LOW: Style issues, minor type mismatches

3. Suggest repair strategy (be specific):
   - "Add import { ref, computed } from 'vue' at top of script"
   - "Fix type annotation: change 'string' to 'Ref<string>'"
   - "Add missing props definition with defineProps<{...}>()"
   - "Fix template binding: change {{ item }} to {{ item.value }}"

4. Estimate difficulty:
   - easy: 1-2 line fix, no refactoring needed
   - medium: Multiple lines or small refactor (add props, fix types)
   - hard: Significant refactor or complex type inference issue

5. Map dependencies:
   - If error A (missing import) causes errors B, C, D (ref not defined), then A blocks B, C, D
   - Fixing root causes should resolve symptoms automatically

Output format: Respond with a JSON object (no markdown, just raw JSON):
{
  "summary": "Brief overview of the error situation (2-3 sentences)",
  "errors": [
    {
      "error_id": "ERROR-001",
      "priority": "CRITICAL",
      "category": "import",
      "root_cause": true,
      "blocks": ["ERROR-002", "ERROR-003"],
      "repair_strategy": "Add import { ref } from 'vue'",
      "estimated_difficulty": "easy"
    }
  ],
  "repair_order": ["ERROR-001", "ERROR-005", ...]
}

Important:
- Be concise but specific in repair strategies
- Identify root causes correctly (look for cascading errors)
- Prioritize fixes that unblock the most other errors
- repair_order should be optimized to minimize total iterations
""",
            markdown=False  # Request raw JSON output
        )

    def _generate_error_id(self, error: Union[ValidationError, RuntimeError], index: int) -> str:
        """
        Generate unique error ID from error properties.

        Args:
            error: ValidationError or RuntimeError
            index: Error index in list

        Returns:
            Unique error ID (e.g., "ERROR-001")
        """
        # Use hash of file + line + message for consistency
        content = f"{error.file}:{error.line}:{error.message}"
        hash_suffix = hashlib.md5(content.encode()).hexdigest()[:6]
        return f"ERROR-{index:03d}-{hash_suffix}"

    def _build_error_context(
        self,
        static_errors: List[ValidationError],
        runtime_errors: List[RuntimeError],
        npm_errors: List[str]
    ) -> str:
        """
        Build context string for LLM analysis.

        Args:
            static_errors: List of static validation errors
            runtime_errors: List of runtime errors
            npm_errors: List of npm error messages

        Returns:
            Formatted context string
        """
        lines = []

        # Static errors
        if static_errors:
            lines.append("=== STATIC VALIDATION ERRORS (vue-tsc) ===")
            for i, error in enumerate(static_errors, 1):
                error_id = self._generate_error_id(error, i)
                lines.append(f"{error_id}: {error.file}:{error.line}")
                lines.append(f"  Code: {error.code}")
                lines.append(f"  Category: {error.category.value}")
                lines.append(f"  Message: {error.message}")
                lines.append("")

        # Runtime errors
        if runtime_errors:
            lines.append("=== RUNTIME ERRORS (Browser) ===")
            for i, error in enumerate(runtime_errors, len(static_errors) + 1):
                error_id = self._generate_error_id(error, i)
                lines.append(f"{error_id}: {error.file}:{error.line}")
                lines.append(f"  Type: {error.error_type}")
                lines.append(f"  Severity: {error.severity}")
                lines.append(f"  Message: {error.message}")
                if error.stack:
                    lines.append(f"  Stack: {error.stack[:200]}...")  # Truncate long stacks
                lines.append("")

        # NPM errors
        if npm_errors:
            lines.append("=== NPM/VITE BUILD ERRORS ===")
            for i, error in enumerate(npm_errors, 1):
                lines.append(f"NPM-{i:03d}: {error}")
            lines.append("")

        return '\n'.join(lines)

    def _parse_analysis(
        self,
        llm_response: str,
        static_errors: List[ValidationError],
        runtime_errors: List[RuntimeError]
    ) -> ErrorReport:
        """
        Parse LLM analysis response into ErrorReport.

        Args:
            llm_response: Raw LLM response (JSON string)
            static_errors: Original static errors
            runtime_errors: Original runtime errors

        Returns:
            Structured ErrorReport
        """
        try:
            # Parse JSON from LLM response
            # Sometimes LLM wraps JSON in markdown code blocks
            response_text = llm_response
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0]
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0]

            analysis = json.loads(response_text.strip())

        except json.JSONDecodeError as e:
            print(f"   ⚠️  Failed to parse LLM response as JSON: {e}")
            print(f"   Response: {llm_response[:500]}...")
            # Fallback to simple analysis
            analysis = self._fallback_analysis(static_errors, runtime_errors)

        # Build error entries
        all_errors = static_errors + runtime_errors
        error_entries: List[ErrorEntry] = []
        error_id_map = {}  # Map error_id to source error

        for i, source_error in enumerate(all_errors, 1):
            error_id = self._generate_error_id(source_error, i)
            error_id_map[error_id] = source_error

            # Find analysis for this error in LLM response
            analysis_entry = None
            for analyzed in analysis.get('errors', []):
                # Match by index or by partial ID match
                if analyzed.get('error_id', '').startswith(f"ERROR-{i:03d}"):
                    analysis_entry = analyzed
                    break

            if analysis_entry:
                error_entries.append(ErrorEntry(
                    error_id=error_id,
                    source_error=source_error,
                    priority=analysis_entry.get('priority', 'MEDIUM'),
                    category=analysis_entry.get('category', 'other'),
                    root_cause=analysis_entry.get('root_cause', False),
                    blocks=analysis_entry.get('blocks', []),
                    repair_strategy=analysis_entry.get('repair_strategy', 'Fix the error'),
                    estimated_difficulty=analysis_entry.get('estimated_difficulty', 'medium')
                ))
            else:
                # Fallback for errors not analyzed by LLM
                error_entries.append(self._create_fallback_entry(error_id, source_error))

        # Build dependency graph
        dependency_graph = {}
        for entry in error_entries:
            if entry.blocks:
                dependency_graph[entry.error_id] = entry.blocks

        # Get repair order from LLM or generate default
        repair_order = analysis.get('repair_order', [])
        if not repair_order:
            # Default: sort by priority
            priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
            sorted_entries = sorted(error_entries, key=lambda e: priority_order.get(e.priority, 4))
            repair_order = [e.error_id for e in sorted_entries]

        return ErrorReport(
            timestamp=datetime.now().isoformat(),
            summary=analysis.get('summary', 'Error analysis completed.'),
            total_errors=len(error_entries),
            errors=error_entries,
            dependency_graph=dependency_graph,
            recommended_repair_order=repair_order
        )

    def _create_fallback_entry(
        self,
        error_id: str,
        source_error: Union[ValidationError, RuntimeError]
    ) -> ErrorEntry:
        """Create a basic error entry when LLM analysis is unavailable."""
        is_static = isinstance(source_error, ValidationError)

        # Determine priority based on error type
        if is_static:
            if source_error.category == ErrorCategory.MISSING_IMPORT:
                priority = 'CRITICAL'
                category = 'import'
                root_cause = True
            elif source_error.category == ErrorCategory.SYNTAX:
                priority = 'CRITICAL'
                category = 'syntax'
                root_cause = True
            elif source_error.category == ErrorCategory.TYPE_INFERENCE:
                priority = 'MEDIUM'
                category = 'type'
                root_cause = False
            else:
                priority = 'MEDIUM'
                category = 'other'
                root_cause = False
        else:
            # Runtime error
            if source_error.error_type == 'exception':
                priority = 'HIGH'
                category = 'runtime'
                root_cause = False
            else:
                priority = 'MEDIUM'
                category = 'runtime'
                root_cause = False

        return ErrorEntry(
            error_id=error_id,
            source_error=source_error,
            priority=priority,
            category=category,
            root_cause=root_cause,
            blocks=[],
            repair_strategy="Review and fix the error",
            estimated_difficulty='medium'
        )

    def _fallback_analysis(
        self,
        static_errors: List[ValidationError],
        runtime_errors: List[RuntimeError]
    ) -> dict:
        """Generate fallback analysis when LLM fails."""
        return {
            'summary': f"Analysis of {len(static_errors)} static and {len(runtime_errors)} runtime errors.",
            'errors': [],
            'repair_order': []
        }

    def categorize_errors(
        self,
        static_errors: List[ValidationError],
        runtime_errors: List[RuntimeError],
        npm_errors: List[str]
    ) -> ErrorReport:
        """
        Main entry point: Analyze all errors and create report.

        Args:
            static_errors: List of static validation errors
            runtime_errors: List of runtime errors
            npm_errors: List of npm error messages

        Returns:
            ErrorReport with prioritized, analyzed errors
        """
        print(f"   Analyzing {len(static_errors)} static + {len(runtime_errors)} runtime errors...")

        # Build context for LLM
        context = self._build_error_context(static_errors, runtime_errors, npm_errors)

        # Run LLM analysis
        prompt = f"""Analyze these errors and categorize:

{context}

Return JSON with:
- summary: brief overview
- errors: list of {{error_id, priority, category, root_cause, blocks, repair_strategy, estimated_difficulty}}
- repair_order: list of error IDs in optimal fix order

Remember:
- Use the exact ERROR-XXX IDs from the context above
- Identify root causes (imports, setup issues) vs symptoms
- Be specific in repair strategies
- Optimize repair_order to fix root causes first
"""

        try:
            response = self.agent.run(prompt)

            # Extract content from response
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)

        except Exception as e:
            print(f"   ⚠️  LLM analysis failed: {e}")
            response_text = "{}"

        # Parse LLM response
        error_report = self._parse_analysis(response_text, static_errors, runtime_errors)

        print(f"   ✅ Error report generated: {error_report.total_errors} errors analyzed")
        return error_report

    def evaluate_repair(
        self,
        before_errors: List[ErrorEntry],
        after_errors: List[ErrorEntry],
        files_changed: List[str]
    ) -> Dict:
        """
        Evaluate repair effectiveness after healer agent runs.

        Args:
            before_errors: Errors before repair
            after_errors: Errors after repair
            files_changed: List of files that were modified

        Returns:
            Dictionary with effectiveness metrics and feedback
        """
        errors_fixed = len(before_errors) - len(after_errors)
        new_errors = 0  # TODO: implement new error detection

        # Simple effectiveness score
        if len(before_errors) > 0:
            effectiveness_score = errors_fixed / len(before_errors)
        else:
            effectiveness_score = 1.0

        feedback = f"Fixed {errors_fixed} errors in {len(files_changed)} files."

        return {
            'errors_fixed': errors_fixed,
            'new_errors_introduced': new_errors,
            'effectiveness_score': effectiveness_score,
            'feedback': feedback
        }
